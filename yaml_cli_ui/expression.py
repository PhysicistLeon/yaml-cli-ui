import ast
import os
import tempfile
from pathlib import Path
from typing import Any


class AttrDict(dict):
    def __getattr__(self, key: str) -> Any:
        if key in self:
            value = self[key]
            return wrap_data(value)
        raise AttributeError(key)


def wrap_data(value: Any) -> Any:
    if isinstance(value, dict):
        return AttrDict({k: wrap_data(v) for k, v in value.items()})
    if isinstance(value, list):
        return [wrap_data(v) for v in value]
    return value


def empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def exists(path: str) -> bool:
    return Path(path).exists()


_ALLOWED_CALLS = {"len": len, "empty": empty, "exists": exists}
_ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
}


class ExpressionError(ValueError):
    pass


def _validate_ast(node: ast.AST) -> None:
    for child in ast.walk(node):
        if type(child) not in _ALLOWED_NODES:
            raise ExpressionError(f"Unsupported expression syntax: {type(child).__name__}")
        if isinstance(child, ast.Call):
            if not isinstance(child.func, ast.Name) or child.func.id not in _ALLOWED_CALLS:
                raise ExpressionError("Only len, empty, exists helpers are supported")


def evaluate_expression(expr: str, context: dict[str, Any]) -> Any:
    try:
        parsed = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression syntax: {expr}") from exc
    _validate_ast(parsed)
    safe_locals = {
        "vars": wrap_data(context.get("vars", {})),
        "form": wrap_data(context.get("form", {})),
        "env": wrap_data(dict(os.environ) | context.get("env", {})),
        "step": wrap_data(context.get("step", {})),
        "cwd": str(Path.cwd()),
        "home": str(Path.home()),
        "temp": tempfile.gettempdir(),
        "os": os.name,
    }
    safe_locals.update(context.get("loop_vars", {}))
    safe_globals = {"__builtins__": {}, **_ALLOWED_CALLS}
    try:
        return eval(compile(parsed, "<expr>", "eval"), safe_globals, safe_locals)
    except Exception as exc:  # noqa: BLE001
        raise ExpressionError(f"Failed to evaluate expression '{expr}': {exc}") from exc


def render_template(raw: Any, context: dict[str, Any]) -> Any:
    if not isinstance(raw, str):
        return raw
    if raw.startswith("${") and raw.endswith("}") and raw.count("${") == 1:
        result = evaluate_expression(raw[2:-1], context)
        return "" if result is None else result

    out = raw
    while "${" in out:
        start = out.find("${")
        end = out.find("}", start)
        if end == -1:
            raise ExpressionError(f"Unclosed template expression: {raw}")
        expr = out[start + 2 : end]
        result = evaluate_expression(expr, context)
        out = out[:start] + ("" if result is None else str(result)) + out[end + 1 :]
    return out
