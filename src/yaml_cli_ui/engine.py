from __future__ import annotations

import ast
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import Any



_TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


class EngineError(RuntimeError):
    pass


class ValidationError(EngineError):
    pass


class ExecutionError(EngineError):
    pass


@dataclass
class StepResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class DotAccessor:
    def __init__(self, value: Any):
        self._value = value

    def __getattr__(self, item: str) -> Any:
        if isinstance(self._value, dict) and item in self._value:
            return wrap(self._value[item])
        raise AttributeError(item)

    def raw(self) -> Any:
        return self._value


def wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return DotAccessor(value)
    return value


class ExpressionEvaluator:
    def __init__(self, context: dict[str, Any]):
        self.context = context

    def eval(self, expression: str) -> Any:
        src = expression.strip()
        if src.startswith("${") and src.endswith("}"):
            src = src[2:-1].strip()
        try:
            node = ast.parse(src, mode="eval")
        except SyntaxError as exc:
            raise ValidationError(f"Invalid expression syntax: {expression}") from exc
        return self._eval_node(node.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.context:
                value = self.context[node.id]
                if isinstance(value, DotAccessor):
                    return value.raw()
                return value
            raise ValidationError(f"Unknown name in expression: {node.id}")
        if isinstance(node, ast.Attribute):
            target = self._eval_node(node.value)
            if isinstance(target, dict):
                return target.get(node.attr)
            raise ValidationError("Attribute access only allowed on objects/maps")
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for part in node.values:
                    result = bool(self._eval_node(part))
                    if not result:
                        return False
                return result
            if isinstance(node.op, ast.Or):
                for part in node.values:
                    value = self._eval_node(part)
                    if value:
                        return True
                return False
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not bool(self._eval_node(node.operand))
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp)
                ok = _compare(op, left, right)
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValidationError("Only direct helper calls are allowed")
            fname = node.func.id
            args = [self._eval_node(arg) for arg in node.args]
            if fname == "len":
                return len(args[0])
            if fname == "empty":
                return is_empty(args[0])
            if fname == "exists":
                return Path(str(args[0])).exists()
            raise ValidationError(f"Unsupported function: {fname}")
        if isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]
        if isinstance(node, ast.Dict):
            return {self._eval_node(k): self._eval_node(v) for k, v in zip(node.keys, node.values)}
        raise ValidationError(f"Unsupported expression node: {type(node).__name__}")


def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    raise ValidationError("Unsupported comparison operator")


def is_empty(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, list) and len(value) == 0)


def render_template(text: str, evaluator: ExpressionEvaluator) -> str:
    def repl(match: re.Match[str]) -> str:
        expr = match.group(1)
        value = evaluator.eval(expr)
        return "" if value is None else str(value)

    return _TEMPLATE_PATTERN.sub(repl, text)


def evaluate_maybe_template(value: Any, evaluator: ExpressionEvaluator) -> Any:
    if isinstance(value, str) and _TEMPLATE_PATTERN.search(value):
        if value.startswith("${") and value.endswith("}") and _TEMPLATE_PATTERN.fullmatch(value):
            return evaluator.eval(value)
        return render_template(value, evaluator)
    return value


class WorkflowEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._validate()

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkflowEngine":
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise ValidationError("PyYAML is required to load workflow files") from exc
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValidationError("YAML root must be a map")
        return cls(data)

    def _validate(self) -> None:
        if self.config.get("version") != 1:
            raise ValidationError("Only version: 1 is supported")
        actions = self.config.get("actions")
        if not isinstance(actions, dict) or not actions:
            raise ValidationError("actions must be a non-empty map")
        for action_id, action in actions.items():
            if not isinstance(action, dict):
                raise ValidationError(f"Action {action_id} must be a map")
            if "title" not in action:
                raise ValidationError(f"Action {action_id} must include title")
            if "pipeline" not in action and "run" not in action:
                raise ValidationError(f"Action {action_id} must include pipeline or run")

    def action_ids(self) -> list[str]:
        return list(self.config["actions"].keys())

    def get_action(self, action_id: str) -> dict[str, Any]:
        return self.config["actions"][action_id]

    def compute_vars(self, form_data: dict[str, Any]) -> dict[str, Any]:
        evaluator = ExpressionEvaluator(self._build_context(form_data, {}, {}))
        out: dict[str, Any] = {}
        for key, raw in (self.config.get("vars") or {}).items():
            if isinstance(raw, dict):
                value = raw.get("default")
            else:
                value = raw
            out[key] = evaluate_maybe_template(value, evaluator)
        return out

    def run_action(self, action_id: str, form_data: dict[str, Any]) -> tuple[list[tuple[str, list[str]]], dict[str, StepResult]]:
        action = self.get_action(action_id)
        pipeline = action.get("pipeline")
        if pipeline is None:
            pipeline = [{"id": f"{action_id}_run", "run": action["run"]}]
        variables = self.compute_vars(form_data)
        step_results: dict[str, StepResult] = {}
        commands: list[tuple[str, list[str]]] = []
        self._run_steps(pipeline, form_data, variables, step_results, {}, commands)
        return commands, step_results

    def _build_context(
        self,
        form_data: dict[str, Any],
        variables: dict[str, Any],
        step_results: dict[str, Any],
        loop_vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        env = dict(os.environ)
        ctx = {
            "form": form_data,
            "vars": variables,
            "env": env,
            "step": {k: {"exit_code": v.exit_code, "stdout": v.stdout, "stderr": v.stderr, "duration_ms": v.duration_ms} for k, v in step_results.items()},
            "cwd": str(Path.cwd()),
            "home": str(Path.home()),
            "temp": str(Path(gettempdir())),
            "os": os.name,
        }
        if loop_vars:
            ctx.update(loop_vars)
        return ctx

    def _run_steps(
        self,
        steps: list[dict[str, Any]],
        form_data: dict[str, Any],
        variables: dict[str, Any],
        step_results: dict[str, StepResult],
        loop_vars: dict[str, Any],
        commands: list[tuple[str, list[str]]],
    ) -> None:
        for step in steps:
            step_id = step.get("id") or f"step_{len(step_results) + 1}"
            evaluator = ExpressionEvaluator(self._build_context(form_data, variables, step_results, loop_vars))
            when = step.get("when")
            if when is not None and not bool(evaluate_maybe_template(when, evaluator)):
                continue

            try:
                if "run" in step:
                    result, argv = self._execute_run(step["run"], evaluator)
                    commands.append((step_id, argv))
                    step_results[step_id] = result
                    if result.exit_code != 0 and not step.get("continue_on_error", False):
                        raise ExecutionError(f"Step {step_id} failed with code {result.exit_code}")
                elif "pipeline" in step:
                    self._run_steps(step["pipeline"], form_data, variables, step_results, loop_vars, commands)
                elif "foreach" in step:
                    self._execute_foreach(step["foreach"], form_data, variables, step_results, loop_vars, commands)
                else:
                    raise ValidationError(f"Step {step_id} has no known type")
            except EngineError:
                if step.get("continue_on_error", False):
                    continue
                raise

    def _execute_foreach(
        self,
        definition: dict[str, Any],
        form_data: dict[str, Any],
        variables: dict[str, Any],
        step_results: dict[str, StepResult],
        loop_vars: dict[str, Any],
        commands: list[tuple[str, list[str]]],
    ) -> None:
        evaluator = ExpressionEvaluator(self._build_context(form_data, variables, step_results, loop_vars))
        items = evaluate_maybe_template(definition.get("in"), evaluator)
        if not isinstance(items, list):
            raise ValidationError("foreach.in must evaluate to a list")
        alias = definition.get("as", "item")
        steps = definition.get("steps") or []
        for idx, item in enumerate(items):
            nested_loop = dict(loop_vars)
            nested_loop[alias] = item
            nested_loop["loop"] = {"index": idx}
            self._run_steps(steps, form_data, variables, step_results, nested_loop, commands)

    def _execute_run(self, definition: dict[str, Any], evaluator: ExpressionEvaluator) -> tuple[StepResult, list[str]]:
        program = evaluate_maybe_template(definition.get("program"), evaluator)
        argv = self._serialize_argv(definition.get("argv", []), evaluator)
        cmd = [str(program), *argv]

        shell = bool(definition.get("shell", self.config.get("app", {}).get("shell", False)))
        if shell and os.name == "nt":
            # Explicit support; still defaults to False.
            shell = True
        workdir = evaluate_maybe_template(definition.get("workdir") or self.config.get("app", {}).get("workdir"), evaluator)
        env = dict(os.environ)
        for k, v in (self.config.get("app", {}).get("env") or {}).items():
            env[k] = str(evaluate_maybe_template(v, evaluator))
        for k, v in (definition.get("env") or {}).items():
            env[k] = str(evaluate_maybe_template(v, evaluator))

        stdout_mode = definition.get("stdout", "capture" if definition.get("capture", False) else "inherit")
        stderr_mode = definition.get("stderr", "capture" if definition.get("capture", False) else "inherit")

        stdout_target, stdout_file = _stream_target(stdout_mode, evaluator)
        stderr_target, stderr_file = _stream_target(stderr_mode, evaluator)
        start = time.time()
        completed = subprocess.run(
            cmd,
            shell=shell,
            cwd=workdir,
            env=env,
            stdout=stdout_target,
            stderr=stderr_target,
            text=True,
            timeout=(definition.get("timeout_ms") or 0) / 1000 or None,
            check=False,
        )
        duration = int((time.time() - start) * 1000)
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()
        return StepResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=duration,
        ), cmd

    def _serialize_argv(self, raw_items: list[Any], evaluator: ExpressionEvaluator) -> list[str]:
        if not isinstance(raw_items, list):
            raise ValidationError("argv must be a list")
        out: list[str] = []
        for item in raw_items:
            if isinstance(item, str):
                out.append(str(evaluate_maybe_template(item, evaluator)))
                continue
            if isinstance(item, dict) and "opt" not in item and len(item) == 1:
                opt, raw_value = next(iter(item.items()))
                value = evaluate_maybe_template(raw_value, evaluator)
                out.extend(_serialize_short_map(str(opt), value))
                continue
            if isinstance(item, dict) and "opt" in item:
                out.extend(_serialize_extended(item, evaluator))
                continue
            raise ValidationError(f"Unsupported argv item: {item}")
        return out


def _serialize_short_map(opt: str, value: Any) -> list[str]:
    if value in (None, False, ""):
        return []
    if value is True:
        return [opt]
    if isinstance(value, list):
        result: list[str] = []
        for part in value:
            result.extend([opt, str(part)])
        return result
    return [opt, str(value)]


def _serialize_extended(item: dict[str, Any], evaluator: ExpressionEvaluator) -> list[str]:
    when = item.get("when")
    if when is not None and not bool(evaluate_maybe_template(when, evaluator)):
        return []

    opt = str(item["opt"])
    value = evaluate_maybe_template(item.get("from"), evaluator)
    mode = item.get("mode", "auto")
    style = item.get("style", "separate")
    joiner = item.get("joiner", ",")
    false_opt = item.get("false_opt")
    omit_if_empty = item.get("omit_if_empty", True)

    if mode == "auto":
        if isinstance(value, bool) or value in ("auto", "true", "false"):
            mode = "flag"
        elif isinstance(value, list):
            mode = "repeat"
        else:
            mode = "value"

    if mode == "flag":
        if value in (True, "true"):
            return [opt]
        if value in (False, "false") and false_opt:
            return [str(false_opt)]
        return []

    if omit_if_empty and is_empty(value):
        return []

    template = item.get("template")
    if mode == "value":
        rendered = _render_option_value(value, template)
        return _format_option(opt, rendered, style)

    if mode == "repeat":
        values = value if isinstance(value, list) else [value]
        out: list[str] = []
        for val in values:
            rendered = _render_option_value(val, template)
            out.extend(_format_option(opt, rendered, style))
        return out

    if mode == "join":
        values = value if isinstance(value, list) else [value]
        rendered_values = [_render_option_value(v, template) for v in values]
        joined = joiner.join(rendered_values)
        return _format_option(opt, joined, style)

    raise ValidationError(f"Unsupported extended arg mode: {mode}")


def _render_option_value(value: Any, template: str | None) -> str:
    if template:
        if isinstance(value, dict):
            return template.format(**value)
        return template.format(value=value)
    return str(value)


def _format_option(opt: str, value: str, style: str) -> list[str]:
    if style == "equals":
        return [f"{opt}={value}"]
    return [opt, value]


def _stream_target(mode: str, evaluator: ExpressionEvaluator) -> tuple[Any, Any]:
    if mode == "inherit":
        return None, None
    if mode == "capture":
        return subprocess.PIPE, None
    if isinstance(mode, str) and mode.startswith("file:"):
        raw = mode.split(":", 1)[1]
        path = evaluate_maybe_template(raw, evaluator)
        handle = open(path, "w", encoding="utf-8")
        return handle, handle
    raise ValidationError(f"Unsupported stream mode: {mode}")
