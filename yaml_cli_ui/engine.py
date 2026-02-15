from __future__ import annotations

import ast
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


TEMPLATE_RE = re.compile(r"\$\{([^{}]+)\}")


class EngineError(Exception):
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
            return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, self.context)
        except Exception as exc:
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

                def add(opt_name: str, val: Any | None = None) -> None:
                    if val is None:
                        out.append(opt_name)
                    elif style == "equals":
                        out.append(f"{opt_name}={val}")
                    else:
                        out.extend([opt_name, str(val)])

                if mode == "flag":
                    if value is True:
                        out.append(opt)
                    elif value is False and false_opt:
                        out.append(str(false_opt))
                elif mode == "value":
                    add(opt, value)
                elif mode == "repeat":
                    values = value if isinstance(value, list) else [value]
                    for entry in values:
                        val = template.format(**entry) if template and isinstance(entry, dict) else (template.format(entry) if template else entry)
                        add(opt, val)
                elif mode == "join":
                    values = value if isinstance(value, list) else [value]
                    rendered = []
                    for entry in values:
                        rendered.append(template.format(**entry) if template and isinstance(entry, dict) else (template.format(entry) if template else str(entry)))
                    add(opt, item.get("joiner", ",").join(rendered))
                else:
                    raise EngineError(f"Unknown mode: {mode}")
                continue

            raise EngineError(f"Unsupported argv item: {item}")
        return out

    def run_action(self, action_id: str, form_data: dict[str, Any], log: callable[[str], None]) -> dict[str, Any]:
        actions = self.config.get("actions", {})
        if action_id not in actions:
            raise EngineError(f"Unknown action: {action_id}")
        action = actions[action_id]
        pipeline = action.get("pipeline")
        if pipeline is None and "run" in action:
            pipeline = [{"id": f"{action_id}_run", "run": action["run"]}]
        if not isinstance(pipeline, list):
            raise EngineError("action.pipeline must be a list")

        step_results: dict[str, Any] = {}
        self._run_steps(pipeline, form_data, step_results, log, {})
        return step_results

    def _run_steps(self, steps: list[dict[str, Any]], form_data: dict[str, Any], step_results: dict[str, Any], log: callable[[str], None], scope: dict[str, Any]) -> None:
        for step in steps:
            step_id = step.get("id", f"step_{len(step_results)+1}")
            ctx = self._base_context(form_data, step_results, scope)
            evaluator = SafeEvaluator(ctx)
            if "when" in step and not bool(render_template(step["when"], evaluator)):
                log(f"[skip] {step_id} (when=false)")
                continue
            continue_on_error = bool(step.get("continue_on_error", False))

            try:
                if "run" in step:
                    result = self._run_command(step_id, step["run"], evaluator, log)
                    step_results[step_id] = result.__dict__
                    if result.exit_code != 0 and not continue_on_error:
                        raise EngineError(f"Step {step_id} failed with exit code {result.exit_code}")
                elif "pipeline" in step:
                    nested = step["pipeline"]
                    if not isinstance(nested, list):
                        raise EngineError("pipeline step requires list")
                    self._run_steps(nested, form_data, step_results, log, scope)
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
                        self._run_steps(nested_steps, form_data, step_results, log, local_scope)
                else:
                    raise EngineError(f"Unknown step type in {step_id}")
            except Exception as exc:
                if continue_on_error:
                    log(f"[warn] {step_id}: {exc}")
                    continue
                raise

    def _stream_output(self, name: str, stream: TextIO, collector: list[str], log: callable[[str], None]) -> None:
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

    def _run_command(self, step_id: str, run_def: dict[str, Any], evaluator: SafeEvaluator, log: callable[[str], None]) -> StepResult:
        program = str(render_template(run_def.get("program"), evaluator))
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

        stdout_mode = run_def.get("stdout", "capture" if run_def.get("capture", True) else "inherit")
        stderr_mode = run_def.get("stderr", "capture" if run_def.get("capture", True) else "inherit")

        stdout_target = subprocess.PIPE if stdout_mode == "capture" else None
        stderr_target = subprocess.PIPE if stderr_mode == "capture" else None

        log(f"[run] {step_id}: {program} {argv}")
        start = time.perf_counter()
        proc = subprocess.Popen(
            [program, *argv],
            shell=shell,
            cwd=workdir,
            env=env,
            text=True,
            stdout=stdout_target,
            stderr=stderr_target,
        )

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
        try:
            exit_code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        finally:
            for t in reader_threads:
                t.join()

        duration_ms = int((time.perf_counter() - start) * 1000)

        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)
        if isinstance(stdout_mode, str) and stdout_mode.startswith("file:"):
            Path(str(stdout_mode[5:])).write_text(stdout, encoding="utf-8")
        if isinstance(stderr_mode, str) and stderr_mode.startswith("file:"):
            Path(str(stderr_mode[5:])).write_text(stderr, encoding="utf-8")

        return StepResult(exit_code, stdout, stderr, duration_ms)


def validate_config(config: dict[str, Any]) -> None:
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
