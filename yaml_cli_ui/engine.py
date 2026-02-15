from __future__ import annotations

import json
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .expression import ExpressionError, render_template
from .schema import validate_workflow


class PipelineError(RuntimeError):
    pass


def load_workflow(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    validate_workflow(raw)
    return raw


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _apply_text_template(template: str, value: Any) -> str:
    if isinstance(value, dict):
        return template.format(**value)
    return template.format(value)


def _serialize_extended(item: dict[str, Any], context: dict[str, Any]) -> list[str]:
    if "opt" not in item or "from" not in item:
        raise PipelineError("extended option object requires opt and from")
    when = item.get("when")
    if when is not None:
        when_eval = render_template(when, context)
        if not when_eval:
            return []

    opt = str(render_template(item["opt"], context))
    value = render_template(item["from"], context)
    mode = item.get("mode", "auto")
    if mode == "auto":
        mode = "flag" if isinstance(value, bool) else "repeat" if isinstance(value, list) else "value"
    style = item.get("style", "separate")
    omit_if_empty = item.get("omit_if_empty", True)
    template = item.get("template")

    def as_opt_arg(v: Any) -> list[str]:
        rendered = _apply_text_template(template, v) if template else str(v)
        return [f"{opt}={rendered}"] if style == "equals" else [opt, rendered]

    if mode == "flag":
        if isinstance(value, str) and value in {"auto", "true", "false"}:
            if value == "auto":
                return []
            if value == "true":
                return [opt]
            false_opt = item.get("false_opt")
            return [str(render_template(false_opt, context))] if false_opt else []
        if value is True:
            return [opt]
        if value is False:
            false_opt = item.get("false_opt")
            return [str(render_template(false_opt, context))] if false_opt else []
        return []

    if omit_if_empty and _is_empty(value):
        return []

    if mode == "value":
        return as_opt_arg(value)
    if mode == "repeat":
        if not isinstance(value, list):
            value = [value]
        out: list[str] = []
        for part in value:
            out.extend(as_opt_arg(part))
        return out
    if mode == "join":
        if not isinstance(value, list):
            value = [value]
        joiner = item.get("joiner", ",")
        rendered_items = [_apply_text_template(template, part) if template else str(part) for part in value]
        return as_opt_arg(joiner.join(rendered_items))
    raise PipelineError(f"Unsupported mode: {mode}")


def serialize_argv(argv_def: list[Any], context: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in argv_def:
        if isinstance(item, str):
            out.append(str(render_template(item, context)))
            continue
        if isinstance(item, dict) and len(item) == 1 and "opt" not in item:
            opt, raw_value = next(iter(item.items()))
            value = render_template(raw_value, context)
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
        if isinstance(item, dict):
            out.extend(_serialize_extended(item, context))
            continue
        raise PipelineError(f"Unsupported argv item: {item}")
    return out


class WorkflowEngine:
    def __init__(self, doc: dict[str, Any]):
        self.doc = deepcopy(doc)
        self.step_results: dict[str, Any] = {}

    def _vars_context(self, action_id: str, form: dict[str, Any]) -> dict[str, Any]:
        vars_def = self.doc.get("vars", {})
        vars_values: dict[str, Any] = {}
        context = {
            "vars": vars_values,
            "form": form,
            "step": self.step_results,
            "env": self.doc.get("app", {}).get("env", {}),
            "loop_vars": {},
        }
        for key, spec in vars_def.items():
            if isinstance(spec, dict):
                vars_values[key] = render_template(spec.get("default"), context)
            else:
                vars_values[key] = render_template(spec, context)
        return context

    def run_action(self, action_id: str, form_data: dict[str, Any]) -> dict[str, Any]:
        actions = self.doc["actions"]
        if action_id not in actions:
            raise PipelineError(f"Unknown action: {action_id}")
        action = actions[action_id]
        self.step_results = {}
        context = self._vars_context(action_id, form_data)
        pipeline = action.get("pipeline") or [{"id": f"{action_id}_run", "run": action["run"]}]
        self._run_pipeline(pipeline, context)
        return self.step_results

    def _eval_when(self, step: dict[str, Any], context: dict[str, Any]) -> bool:
        when = step.get("when")
        if when is None:
            return True
        res = render_template(when, context)
        return bool(res)

    def _run_pipeline(self, pipeline: list[dict[str, Any]], context: dict[str, Any]) -> None:
        for step in pipeline:
            step_id = step.get("id") or f"step_{len(self.step_results)}"
            if not self._eval_when(step, context):
                continue
            try:
                if "run" in step:
                    self._run_step(step_id, step["run"], context)
                elif "pipeline" in step:
                    self._run_pipeline(step["pipeline"], context)
                elif "foreach" in step:
                    self._run_foreach(step["foreach"], context)
                else:
                    raise PipelineError(f"Unknown step type in {step_id}")
            except (PipelineError, ExpressionError) as exc:
                if step.get("continue_on_error"):
                    self.step_results[step_id] = {
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": str(exc),
                        "duration_ms": 0,
                    }
                    continue
                raise

    def _run_foreach(self, spec: dict[str, Any], context: dict[str, Any]) -> None:
        items = render_template(spec.get("in"), context)
        if not isinstance(items, list):
            raise PipelineError("foreach.in must evaluate to a list")
        alias = spec.get("as", "item")
        for idx, item in enumerate(items):
            context["loop_vars"][alias] = item
            context["loop_vars"]["loop"] = {"index": idx}
            self._run_pipeline(spec.get("steps", []), context)

    def _run_step(self, step_id: str, run_def: dict[str, Any], context: dict[str, Any]) -> None:
        program = str(render_template(run_def["program"], context))
        argv = serialize_argv(run_def.get("argv", []), context)
        shell = run_def.get("shell", self.doc.get("app", {}).get("shell", False))
        workdir = render_template(run_def.get("workdir", self.doc.get("app", {}).get("workdir")), context)

        env = dict(self.doc.get("app", {}).get("env", {}))
        env.update(run_def.get("env", {}))
        rendered_env = {k: str(render_template(v, context)) for k, v in env.items()}

        stdout_mode = run_def.get("stdout", "capture" if run_def.get("capture") else "inherit")
        stderr_mode = run_def.get("stderr", "capture" if run_def.get("capture") else "inherit")
        timeout_s = None
        if run_def.get("timeout_ms"):
            timeout_s = run_def["timeout_ms"] / 1000.0

        def resolve_stream(mode: str):
            if mode == "inherit":
                return None
            if mode == "capture":
                return subprocess.PIPE
            if str(mode).startswith("file:"):
                path = str(mode)[5:]
                return open(path, "a", encoding="utf-8")
            raise PipelineError(f"Unsupported stream mode: {mode}")

        stdout_target = resolve_stream(stdout_mode)
        stderr_target = resolve_stream(stderr_mode)

        start = time.perf_counter()
        completed = subprocess.run(
            [program, *argv],
            shell=bool(shell),
            cwd=str(workdir) if workdir else None,
            env=None if not rendered_env else rendered_env,
            stdout=stdout_target,
            stderr=stderr_target,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        stdout = completed.stdout if completed.stdout is not None else ""
        stderr = completed.stderr if completed.stderr is not None else ""
        self.step_results[step_id] = {
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
        }
        context["step"] = self.step_results

        if completed.returncode != 0:
            raise PipelineError(f"Step {step_id} failed with exit code {completed.returncode}")


def parse_structured_field(raw: str, field_type: str) -> Any:
    if field_type in {"kv_list", "struct_list", "multichoice", "path"}:
        if raw.strip() == "":
            return []
        return json.loads(raw)
    return raw
