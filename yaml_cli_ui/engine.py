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

TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")


class EngineError(Exception):
    pass


@dataclass
class StepResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class SafeExprEvaluator(ast.NodeVisitor):
    def __init__(self, scope: dict[str, Any]):
        self.scope = scope

    def eval(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise EngineError(f"Invalid expression syntax: {expr}") from exc
        return self.visit(tree.body)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.scope:
            return self.scope[node.id]
        raise EngineError(f"Unknown name in expression: {node.id}")

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        base = self.visit(node.value)
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        base = self.visit(node.value)
        idx = self.visit(node.slice)
        return base[idx]

    def visit_List(self, node: ast.List) -> list[Any]:
        return [self.visit(el) for el in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.visit(el) for el in node.elts)

    def visit_Dict(self, node: ast.Dict) -> dict[Any, Any]:
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise EngineError("Unsupported unary operator")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise EngineError("Unsupported bool operator")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, cmp in zip(node.ops, node.comparators):
            right = self.visit(cmp)
            ok = self._cmp(op, left, right)
            if not ok:
                return False
            left = right
        return True

    def _cmp(self, op: ast.cmpop, left: Any, right: Any) -> bool:
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
        raise EngineError("Unsupported compare operator")

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        args = [self.visit(a) for a in node.args]
        if node.keywords:
            raise EngineError("Keyword arguments are not supported")
        if func not in (len, _empty, _exists):
            raise EngineError("Function not allowed")
        return func(*args)

    def generic_visit(self, node: ast.AST) -> Any:
        raise EngineError(f"Unsupported expression construct: {type(node).__name__}")


def _empty(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, list) and len(value) == 0)


def _exists(path: str) -> bool:
    return Path(path).exists()


class PipelineEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def _base_scope(self, form_data: dict[str, Any], step_data: dict[str, Any], local: dict[str, Any] | None = None) -> dict[str, Any]:
        local = local or {}
        return {
            "vars": self.resolve_vars(form_data),
            "form": form_data,
            "env": dict(os.environ),
            "cwd": os.getcwd(),
            "home": str(Path.home()),
            "temp": gettempdir(),
            "os": os.name,
            "step": step_data,
            "len": len,
            "empty": _empty,
            "exists": _exists,
            **local,
        }

    def resolve_expr(self, expr: str, scope: dict[str, Any]) -> Any:
        evaluator = SafeExprEvaluator(scope)
        return evaluator.eval(expr)

    def render_template(self, value: str, scope: dict[str, Any]) -> str:
        def _replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            result = self.resolve_expr(expr, scope)
            return "" if result is None else str(result)

        return TEMPLATE_RE.sub(_replace, value)

    def eval_template_value(self, value: Any, scope: dict[str, Any]) -> Any:
        if isinstance(value, str):
            m = TEMPLATE_RE.fullmatch(value.strip())
            if m:
                return self.resolve_expr(m.group(1).strip(), scope)
            return self.render_template(value, scope)
        if isinstance(value, list):
            return [self.eval_template_value(v, scope) for v in value]
        if isinstance(value, dict):
            return {k: self.eval_template_value(v, scope) for k, v in value.items()}
        return value

    def resolve_vars(self, form_data: dict[str, Any]) -> dict[str, Any]:
        vars_cfg = self.config.get("vars", {})
        resolved: dict[str, Any] = {}
        for key, value in vars_cfg.items():
            if isinstance(value, dict) and "type" in value:
                default = value.get("default")
                resolved[key] = self.eval_template_value(default, {"vars": resolved, "form": form_data, "home": str(Path.home()), "cwd": os.getcwd(), "temp": gettempdir(), "env": dict(os.environ), "os": os.name, "len": len, "empty": _empty, "exists": _exists})
            else:
                resolved[key] = self.eval_template_value(value, {"vars": resolved, "form": form_data, "home": str(Path.home()), "cwd": os.getcwd(), "temp": gettempdir(), "env": dict(os.environ), "os": os.name, "len": len, "empty": _empty, "exists": _exists})
        return resolved

    def build_argv(self, argv_cfg: list[Any], scope: dict[str, Any]) -> list[str]:
        argv: list[str] = []
        for item in argv_cfg:
            if isinstance(item, str):
                argv.append(str(self.eval_template_value(item, scope)))
                continue
            if isinstance(item, dict) and len(item) == 1 and "opt" not in item:
                opt, raw = next(iter(item.items()))
                value = self.eval_template_value(raw, scope)
                if value is True:
                    argv.append(opt)
                elif value in (False, None, ""):
                    continue
                elif isinstance(value, list):
                    for v in value:
                        argv.extend([opt, str(v)])
                else:
                    argv.extend([opt, str(value)])
                continue
            if isinstance(item, dict) and "opt" in item:
                self._append_extended_arg(argv, item, scope)
                continue
            raise EngineError(f"Unsupported argv item: {item}")
        return argv

    def _append_extended_arg(self, argv: list[str], cfg: dict[str, Any], scope: dict[str, Any]) -> None:
        opt = cfg["opt"]
        when = cfg.get("when")
        if when is not None and not bool(self.eval_template_value(when, scope)):
            return
        value = self.eval_template_value(cfg.get("from"), scope)
        mode = cfg.get("mode", "auto")
        style = cfg.get("style", "separate")
        omit_if_empty = cfg.get("omit_if_empty", True)
        template = cfg.get("template")
        joiner = cfg.get("joiner", ",")
        false_opt = cfg.get("false_opt")

        if mode == "auto":
            if isinstance(value, bool) or value in ("auto", "true", "false"):
                mode = "flag"
            elif isinstance(value, list):
                mode = "repeat"
            else:
                mode = "value"

        if mode == "flag":
            if value in ("auto", None):
                return
            if value in (False, "false"):
                if false_opt:
                    argv.append(false_opt)
                return
            if value in (True, "true"):
                argv.append(opt)
                return

        if omit_if_empty and _empty(value):
            return

        if mode == "value":
            self._emit_opt(argv, opt, str(value), style)
            return

        if mode == "repeat":
            values = value if isinstance(value, list) else [value]
            for raw in values:
                rendered = template.format(**raw) if template and isinstance(raw, dict) else (template.format(raw) if template else raw)
                self._emit_opt(argv, opt, str(rendered), style)
            return

        if mode == "join":
            values = value if isinstance(value, list) else [value]
            rendered_vals = []
            for raw in values:
                rendered_vals.append(template.format(**raw) if template and isinstance(raw, dict) else (template.format(raw) if template else str(raw)))
            self._emit_opt(argv, opt, joiner.join(rendered_vals), style)
            return

        raise EngineError(f"Unsupported arg mode: {mode}")

    @staticmethod
    def _emit_opt(argv: list[str], opt: str, val: str, style: str) -> None:
        if style == "separate":
            argv.extend([opt, val])
        elif style == "equals":
            argv.append(f"{opt}={val}")
        else:
            raise EngineError(f"Unsupported style: {style}")

    def run_action(self, action_id: str, form_data: dict[str, Any]) -> dict[str, StepResult]:
        actions = self.config.get("actions", {})
        action = actions[action_id]
        pipeline = action.get("pipeline")
        if pipeline is None and action.get("run"):
            pipeline = [{"id": f"{action_id}_run", "run": action["run"]}]
        if not isinstance(pipeline, list):
            raise EngineError("Action pipeline must be a list")
        results: dict[str, StepResult] = {}
        self._run_steps(pipeline, form_data, results, {})
        return results

    def _run_steps(self, steps: list[dict[str, Any]], form_data: dict[str, Any], results: dict[str, StepResult], local: dict[str, Any]) -> None:
        for step in steps:
            step_id = step.get("id") or f"step_{len(results)+1}"
            scope = self._base_scope(form_data, {k: vars(v) for k, v in results.items()}, local)
            if "when" in step and not bool(self.eval_template_value(step["when"], scope)):
                continue

            try:
                if "run" in step:
                    result = self._run_command(step["run"], scope)
                    results[step_id] = result
                    if result.exit_code != 0 and not step.get("continue_on_error", False):
                        raise EngineError(f"Step {step_id} failed with exit code {result.exit_code}")
                elif "pipeline" in step:
                    nested = step["pipeline"]
                    if not isinstance(nested, list):
                        raise EngineError("Nested pipeline must be a list")
                    self._run_steps(nested, form_data, results, local)
                elif "foreach" in step:
                    loop = step["foreach"]
                    items = self.eval_template_value(loop.get("in"), scope)
                    if not isinstance(items, list):
                        raise EngineError("foreach.in must evaluate to a list")
                    var_name = loop.get("as", "item")
                    for idx, item in enumerate(items):
                        child_local = dict(local)
                        child_local[var_name] = item
                        child_local["loop"] = {"index": idx}
                        self._run_steps(loop.get("steps", []), form_data, results, child_local)
                else:
                    raise EngineError(f"Unsupported step type in step {step_id}")
            except Exception:
                if step.get("continue_on_error", False):
                    continue
                raise

    def _run_command(self, run_cfg: dict[str, Any], scope: dict[str, Any]) -> StepResult:
        program = self.eval_template_value(run_cfg["program"], scope)
        argv_cfg = run_cfg.get("argv", [])
        argv = [str(program), *self.build_argv(argv_cfg, scope)]

        workdir = self.eval_template_value(run_cfg.get("workdir"), scope) if run_cfg.get("workdir") else self.config.get("app", {}).get("workdir")
        shell = run_cfg.get("shell", self.config.get("app", {}).get("shell", False))

        env = dict(os.environ)
        app_env = self.config.get("app", {}).get("env", {})
        env.update({k: str(self.eval_template_value(v, scope)) for k, v in app_env.items()})
        run_env = run_cfg.get("env", {})
        env.update({k: str(self.eval_template_value(v, scope)) for k, v in run_env.items()})

        stdout_mode = run_cfg.get("stdout", "capture" if run_cfg.get("capture") else "inherit")
        stderr_mode = run_cfg.get("stderr", "capture" if run_cfg.get("capture") else "inherit")

        stdout_target, stdout_file = self._stream_target(stdout_mode, scope)
        stderr_target, stderr_file = self._stream_target(stderr_mode, scope)

        started = time.perf_counter()
        completed = subprocess.run(
            argv,
            shell=bool(shell),
            cwd=workdir,
            env=env,
            timeout=(run_cfg.get("timeout_ms") or 0) / 1000 or None,
            text=True,
            stdout=None if stdout_target == "inherit" else stdout_target,
            stderr=None if stderr_target == "inherit" else stderr_target,
            check=False,
        )
        duration = int((time.perf_counter() - started) * 1000)

        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()

        return StepResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=duration,
        )

    def _stream_target(self, mode: str, scope: dict[str, Any]) -> tuple[Any, Any]:
        if mode == "inherit":
            return "inherit", None
        if mode == "capture":
            return subprocess.PIPE, None
        if mode.startswith("file:"):
            path = self.render_template(mode[5:], scope)
            handle = open(path, "w", encoding="utf-8")
            return handle, handle
        raise EngineError(f"Unsupported stream mode: {mode}")


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != 1:
        raise EngineError("Only version: 1 is supported")
    if "actions" not in config or not isinstance(config["actions"], dict):
        raise EngineError("actions must be a mapping")
    for action_id, action in config["actions"].items():
        if "title" not in action:
            raise EngineError(f"Action {action_id} is missing title")
        if "pipeline" not in action and "run" not in action:
            raise EngineError(f"Action {action_id} must contain pipeline or run")
