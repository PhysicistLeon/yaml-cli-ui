from __future__ import annotations

import ast
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, TextIO


TEMPLATE_RE = re.compile(r"\$\{([^{}]+)\}")


class EngineError(Exception):
    pass


class ActionCancelledError(EngineError):
    pass


class DotDict:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, item: str) -> Any:
        if item not in self._data:
            raise AttributeError(item)
        return to_dotdict(self._data[item])

    def __getitem__(self, item: str) -> Any:
        return to_dotdict(self._data[item])

    def get(self, key: str, default: Any = None) -> Any:
        return to_dotdict(self._data.get(key, default))


def to_dotdict(value: Any) -> Any:
    if isinstance(value, dict) and not isinstance(value, DotDict):
        return DotDict({k: to_dotdict(v) for k, v in value.items()})
    if isinstance(value, list):
        return [to_dotdict(v) for v in value]
    return value


def empty(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, list) and len(value) == 0)


class SafeEvaluator:
    ALLOWED = (
        ast.Expression,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Attribute,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.UnaryOp,
        ast.Not,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Call,
        ast.Subscript,
        ast.Index,
        ast.List,
        ast.Tuple,
        ast.Dict,
    )

    def __init__(self, context: dict[str, Any]):
        self.context = context

    def eval(self, expression: str) -> Any:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise EngineError(f"Invalid expression syntax: {expression}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, self.ALLOWED):
                raise EngineError(f"Forbidden expression construct: {type(node).__name__}")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in {"len", "empty", "exists"}:
                    raise EngineError("Only len/empty/exists calls are allowed")
        try:
            # Controlled eval over a pre-validated AST and empty builtins.
            return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, self.context)  # pylint: disable=eval-used
        except (NameError, AttributeError, KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise EngineError(f"Expression evaluation failed: {expression}: {exc}") from exc


def render_template(value: Any, evaluator: SafeEvaluator) -> Any:
    if not isinstance(value, str):
        return value
    whole = TEMPLATE_RE.fullmatch(value.strip())
    if whole:
        result = evaluator.eval(whole.group(1).strip())
        return "" if result is None else result

    def _replace(match: re.Match[str]) -> str:
        result = evaluator.eval(match.group(1).strip())
        return "" if result is None else str(result)

    return TEMPLATE_RE.sub(_replace, value)


@dataclass
class StepResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class PipelineEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._lock = threading.Lock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._active_runs: dict[str, int] = {}
        self._running_processes: dict[str, list[subprocess.Popen[str]]] = {}

    def _looks_like_python_program(self, program: str) -> bool:
        name = Path(program).name.lower()
        return name in {"python", "python.exe", "python3", "python3.exe"}

    def _sanitize_child_env_for_embedded_tk(self, env: dict[str, str]) -> dict[str, str]:
        sanitized = dict(env)
        for key in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH", "PYTHONHOME", "PYTHONPATH"):
            sanitized.pop(key, None)
        for key, value in list(sanitized.items()):
            if isinstance(value, str) and "_MEI" in value:
                sanitized.pop(key, None)
        return sanitized

    def stop_action(self, action_id: str) -> None:
        with self._lock:
            event = self._cancel_events.get(action_id)
            processes = list(self._running_processes.get(action_id, []))
        if event is not None:
            event.set()
        for proc in processes:
            if proc.poll() is None:
                self._terminate_process(proc)

    def _terminate_process(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.poll() is None:
                proc.terminate()

    def _base_context(self, form_data: dict[str, Any], step_results: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_vars = {}
        vars_def = self.config.get("vars", {})
        for key, value in vars_def.items():
            if isinstance(value, dict) and "default" in value:
                resolved_vars[key] = value["default"]
            else:
                resolved_vars[key] = value

        ctx = {
            "vars": to_dotdict(resolved_vars),
            "form": to_dotdict(form_data),
            "env": to_dotdict(dict(os.environ)),
            "step": to_dotdict(step_results),
            "cwd": os.getcwd(),
            "home": str(Path.home()),
            "temp": tempfile.gettempdir(),
            "os": os.name,
            "len": len,
            "empty": empty,
            "exists": lambda p: Path(str(p)).exists(),
        }
        if extra:
            ctx.update(extra)
        evalr = SafeEvaluator(ctx)

        for key, val in list(resolved_vars.items()):
            resolved_vars[key] = render_template(val, evalr)
        ctx["vars"] = to_dotdict(resolved_vars)
        return ctx

    def serialize_argv(self, argv_def: list[Any], evaluator: SafeEvaluator) -> list[str]:
        out: list[str] = []
        for item in argv_def:
            if isinstance(item, str):
                rendered = render_template(item, evaluator)
                out.append(str(rendered))
                continue
            if isinstance(item, dict) and len(item) == 1 and "opt" not in item:
                opt, value_expr = next(iter(item.items()))
                value = render_template(value_expr, evaluator)
                if value is True:
                    out.append(str(opt))
                elif value is False or value is None or value == "":
                    continue
                elif isinstance(value, list):
                    for v in value:
                        out.extend([str(opt), str(v)])
                else:
                    out.extend([str(opt), str(value)])
                continue
            if isinstance(item, dict) and "opt" in item:
                when = item.get("when")
                if when is not None and not bool(render_template(when, evaluator)):
                    continue
                opt = str(item["opt"])
                value = render_template(item.get("from"), evaluator)
                mode = item.get("mode", "auto")
                style = item.get("style", "separate")
                omit_if_empty = item.get("omit_if_empty", True)
                template = item.get("template")
                false_opt = item.get("false_opt")
                if mode == "auto":
                    if isinstance(value, bool):
                        mode = "flag"
                    elif isinstance(value, list):
                        mode = "repeat"
                    else:
                        mode = "value"

                if isinstance(value, str) and value in {"auto", "true", "false"}:
                    if value == "auto":
                        continue
                    if value == "true":
                        out.append(opt)
                        continue
                    if false_opt:
                        out.append(str(false_opt))
                    continue

                if omit_if_empty and empty(value):
                    continue

                if mode == "flag":
                    if value is True:
                        out.append(opt)
                    elif value is False and false_opt:
                        out.append(str(false_opt))
                elif mode == "value":
                    self._append_option(out, opt, style, value)
                elif mode == "repeat":
                    values = value if isinstance(value, list) else [value]
                    for entry in values:
                        val = template.format(**entry) if template and isinstance(entry, dict) else (template.format(entry) if template else entry)
                        self._append_option(out, opt, style, val)
                elif mode == "join":
                    values = value if isinstance(value, list) else [value]
                    rendered = []
                    for entry in values:
                        rendered.append(template.format(**entry) if template and isinstance(entry, dict) else (template.format(entry) if template else str(entry)))
                    self._append_option(out, opt, style, item.get("joiner", ",").join(rendered))
                else:
                    raise EngineError(f"Unknown mode: {mode}")
                continue

            raise EngineError(f"Unsupported argv item: {item}")
        return out

    @staticmethod
    def _append_option(out: list[str], opt_name: str, style: str, val: Any | None = None) -> None:
        if val is None:
            out.append(opt_name)
        elif style == "equals":
            out.append(f"{opt_name}={val}")
        else:
            out.extend([opt_name, str(val)])

    def _resolve_program(self, program: str, evaluator: SafeEvaluator) -> str:
        runtime = self.config.get("runtime", {})
        python_runtime = runtime.get("python", {}) if isinstance(runtime, dict) else {}
        python_executable = python_runtime.get("executable") if isinstance(python_runtime, dict) else None
        if program == "python" and python_executable:
            return str(render_template(python_executable, evaluator))
        return program

    def run_action(self, action_id: str, form_data: dict[str, Any], log: Callable[[str], None]) -> dict[str, Any]:
        actions = self.config.get("actions", {})
        if action_id not in actions:
            raise EngineError(f"Unknown action: {action_id}")
        action = actions[action_id]
        pipeline = action.get("pipeline")
        if pipeline is None and "run" in action:
            pipeline = [{"id": f"{action_id}_run", "run": action["run"]}]
        if not isinstance(pipeline, list):
            raise EngineError("action.pipeline must be a list")

        with self._lock:
            event = self._cancel_events.get(action_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[action_id] = event
            event.clear()
            self._active_runs[action_id] = self._active_runs.get(action_id, 0) + 1

        try:
            step_results: dict[str, Any] = {}
            self._run_steps(pipeline, form_data, step_results, log, {}, action_id, event)
            return step_results
        finally:
            with self._lock:
                remaining = self._active_runs.get(action_id, 1) - 1
                if remaining <= 0:
                    self._active_runs.pop(action_id, None)
                    self._cancel_events.pop(action_id, None)
                    self._running_processes.pop(action_id, None)
                else:
                    self._active_runs[action_id] = remaining

    def _run_steps(
        self,
        steps: list[dict[str, Any]],
        form_data: dict[str, Any],
        step_results: dict[str, Any],
        log: Callable[[str], None],
        scope: dict[str, Any],
        action_id: str,
        cancel_event: threading.Event,
    ) -> None:
        for step in steps:
            if cancel_event.is_set():
                raise ActionCancelledError("Action was stopped by user")
            step_id = step.get("id", f"step_{len(step_results)+1}")
            ctx = self._base_context(form_data, step_results, scope)
            evaluator = SafeEvaluator(ctx)
            if "when" in step and not bool(render_template(step["when"], evaluator)):
                log(f"[skip] {step_id} (when=false)")
                continue
            continue_on_error = bool(step.get("continue_on_error", False))

            try:
                if "run" in step:
                    result = self._run_command(step_id, step["run"], evaluator, log, action_id, cancel_event)
                    step_results[step_id] = result.__dict__
                    if result.exit_code != 0 and not continue_on_error:
                        raise EngineError(f"Step {step_id} failed with exit code {result.exit_code}")
                elif "pipeline" in step:
                    nested = step["pipeline"]
                    if not isinstance(nested, list):
                        raise EngineError("pipeline step requires list")
                    self._run_steps(nested, form_data, step_results, log, scope, action_id, cancel_event)
                elif "foreach" in step:
                    foreach = step["foreach"]
                    items = render_template(foreach.get("in"), evaluator)
                    if not isinstance(items, list):
                        raise EngineError("foreach.in must evaluate to list")
                    var_name = foreach.get("as", "item")
                    nested_steps = foreach.get("steps", [])
                    for index, value in enumerate(items):
                        local_scope = dict(scope)
                        local_scope[var_name] = to_dotdict(value)
                        local_scope["loop"] = to_dotdict({"index": index})
                        self._run_steps(nested_steps, form_data, step_results, log, local_scope, action_id, cancel_event)
                else:
                    raise EngineError(f"Unknown step type in {step_id}")
            except (EngineError, ActionCancelledError, OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as exc:
                if continue_on_error:
                    log(f"[warn] {step_id}: {exc}")
                    continue
                raise

    def _stream_output(self, name: str, stream: TextIO, collector: list[str], log: Callable[[str], None]) -> None:
        buffer = ""
        while True:
            chunk = stream.read(1)
            if chunk == "":
                break
            if chunk in ("\n", "\r"):
                if buffer:
                    collector.append(buffer)
                    log(f"[{name}] {buffer}")
                    buffer = ""
            else:
                buffer += chunk
        if buffer:
            collector.append(buffer)
            log(f"[{name}] {buffer}")

    def _run_command(
        self,
        step_id: str,
        run_def: dict[str, Any],
        evaluator: SafeEvaluator,
        log: Callable[[str], None],
        action_id: str,
        cancel_event: threading.Event,
    ) -> StepResult:
        raw_program = str(render_template(run_def.get("program"), evaluator))
        program = self._resolve_program(raw_program, evaluator)
        argv_def = run_def.get("argv", [])
        argv = self.serialize_argv(argv_def, evaluator)
        shell = bool(run_def.get("shell", self.config.get("app", {}).get("shell", False)))
        timeout_ms = run_def.get("timeout_ms")
        workdir = run_def.get("workdir") or self.config.get("app", {}).get("workdir")
        workdir = render_template(workdir, evaluator) if workdir else None

        env = dict(os.environ)
        for k, v in self.config.get("app", {}).get("env", {}).items():
            env[k] = str(render_template(v, evaluator))
        for k, v in run_def.get("env", {}).items():
            env[k] = str(render_template(v, evaluator))
        if getattr(sys, "frozen", False) and self._looks_like_python_program(program):
            env = self._sanitize_child_env_for_embedded_tk(env)

        stdout_mode = run_def.get("stdout", "capture" if run_def.get("capture", True) else "inherit")
        stderr_mode = run_def.get("stderr", "capture" if run_def.get("capture", True) else "inherit")

        stdout_target = subprocess.PIPE if stdout_mode == "capture" else None
        stderr_target = subprocess.PIPE if stderr_mode == "capture" else None

        log(f"[run] {step_id}: {program} {argv}")
        start = time.perf_counter()
        popen_kwargs: dict[str, Any] = {}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        with subprocess.Popen(
            [program, *argv],
            shell=shell,
            cwd=workdir,
            env=env,
            text=True,
            stdout=stdout_target,
            stderr=stderr_target,
            **popen_kwargs,
        ) as proc:
            with self._lock:
                self._running_processes.setdefault(action_id, []).append(proc)

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            reader_threads: list[threading.Thread] = []

            if proc.stdout is not None:
                t = threading.Thread(target=self._stream_output, args=("stdout", proc.stdout, stdout_lines, log), daemon=True)
                reader_threads.append(t)
                t.start()
            if proc.stderr is not None:
                t = threading.Thread(target=self._stream_output, args=("stderr", proc.stderr, stderr_lines, log), daemon=True)
                reader_threads.append(t)
                t.start()

            timeout_s = (timeout_ms / 1000.0) if timeout_ms else None
            deadline = (start + timeout_s) if timeout_s is not None else None
            try:
                while True:
                    if cancel_event.is_set():
                        self._terminate_process(proc)
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            if os.name != "nt":
                                try:
                                    os.killpg(proc.pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                            else:
                                proc.kill()
                            proc.wait()
                        raise ActionCancelledError("Action was stopped by user")

                    if deadline is not None and time.perf_counter() >= deadline:
                        proc.kill()
                        proc.wait()
                        raise subprocess.TimeoutExpired([program, *argv], timeout_s)

                    try:
                        exit_code = proc.wait(timeout=0.1)
                        if cancel_event.is_set():
                            raise ActionCancelledError("Action was stopped by user")
                        break
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                for t in reader_threads:
                    t.join()
                with self._lock:
                    processes = self._running_processes.get(action_id, [])
                    if proc in processes:
                        processes.remove(proc)

            duration_ms = int((time.perf_counter() - start) * 1000)

        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)
        if isinstance(stdout_mode, str) and stdout_mode.startswith("file:"):
            Path(str(stdout_mode[5:])).write_text(stdout, encoding="utf-8")
        if isinstance(stderr_mode, str) and stderr_mode.startswith("file:"):
            Path(str(stderr_mode[5:])).write_text(stderr, encoding="utf-8")

        return StepResult(exit_code, stdout, stderr, duration_ms)


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise EngineError("Config root must be a mapping")
    if config.get("version") != 1:
        raise EngineError("Only version=1 is supported")
    actions = config.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise EngineError("actions must be a non-empty map")
    for aid, action in actions.items():
        if "title" not in action:
            raise EngineError(f"action {aid} requires title")
        if "pipeline" not in action and "run" not in action:
            raise EngineError(f"action {aid} requires pipeline or run")
        if "pipeline" in action and not isinstance(action["pipeline"], list):
            raise EngineError(f"action {aid}.pipeline must be list")
