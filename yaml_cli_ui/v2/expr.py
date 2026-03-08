"""Safe expression evaluation for YAML CLI UI v2."""

from __future__ import annotations

import ast
from dataclasses import is_dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._template_utils import find_closing_brace
from .errors import V2ExpressionError

_EXPLICIT_ROOT_NAMESPACES = ("params", "locals", "profile", "steps", "run", "loop", "error")
_SHORT_NAME_NAMESPACES = ("bindings", "params", "locals", "run", "loop", "error")


def resolve_name(name: str, context: Mapping[str, Any] | Any) -> Any:
    """Resolve short or namespaced reference against context."""

    normalized = name.strip()
    if not normalized:
        raise V2ExpressionError("cannot resolve empty name")

    if "." in normalized or "[" in normalized:
        root, remainder = _split_reference(normalized)
        context_roots = _context_keys(context)
        if root not in _EXPLICIT_ROOT_NAMESPACES and root not in context_roots:
            raise V2ExpressionError(
                f"unsupported reference root '{root}' in '{name}'; use explicit namespace"
            )
        base = _get_from_context(context, root)
        if remainder == "":
            return base
        return _resolve_path(base, remainder, original=name)

    try:
        bindings = _get_from_context(context, "bindings")
        return _get_member(bindings, normalized)
    except V2ExpressionError:
        pass

    matches: list[tuple[str, Any]] = []
    for namespace in _SHORT_NAME_NAMESPACES:
        if namespace == "bindings":
            continue
        try:
            bucket = _get_from_context(context, namespace)
            value = _get_member(bucket, normalized)
            matches.append((namespace, value))
        except V2ExpressionError:
            continue

    if not matches:
        raise V2ExpressionError(f"unresolved name '{name}'")
    if len(matches) > 1:
        namespaces = ", ".join(ns for ns, _ in matches)
        raise V2ExpressionError(
            f"ambiguous short name '{name}'; found in namespaces: {namespaces}"
        )
    return matches[0][1]


def evaluate_expression(expr: str, context: Mapping[str, Any] | Any) -> Any:
    """Evaluate expression with AST allowlist and restricted builtins."""

    if not isinstance(expr, str):
        raise V2ExpressionError(f"expression must be string, got {type(expr).__name__}")

    normalized = _unwrap_expr(expr)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise V2ExpressionError(f"invalid expression '{expr}': {exc.msg}") from exc

    evaluator = _SafeEvaluator(normalized, context)
    return evaluator.evaluate(tree.body)


def extract_local_refs(value: str) -> set[str]:
    """Extract direct `locals.<name>` references from a string value."""

    refs: set[str] = set()
    if not isinstance(value, str):
        return refs

    i = 0
    length = len(value)
    while i < length:
        if value.startswith("$${", i):
            i += 3
            continue
        if value.startswith("$$", i):
            i += 2
            continue
        if value.startswith("$locals.", i):
            name, end = _read_identifier(value, i + len("$locals."))
            if name:
                refs.add(name)
                i = end
                continue
        if value.startswith("${", i):
            end = find_closing_brace(value, i + 2)
            inner = value[i + 2 : end]
            refs.update(_extract_locals_from_expr(inner))
            i = end + 1
            continue
        i += 1
    return refs


class _SafeEvaluator:
    def __init__(self, raw_expression: str, context: Mapping[str, Any] | Any) -> None:
        self._expression = raw_expression
        self._context = context

    def evaluate(self, node: ast.AST) -> Any:
        handlers: tuple[tuple[type[ast.AST], Any], ...] = (
            (ast.Constant, lambda n: n.value),
            (ast.Name, self._eval_name),
            (ast.BoolOp, self._eval_bool_op),
            (ast.UnaryOp, self._eval_unary_op),
            (ast.Compare, self._eval_compare),
            (ast.Attribute, self._eval_attribute),
            (ast.Subscript, self._eval_subscript),
            (ast.Call, self._eval_call),
            (ast.List, lambda n: [self.evaluate(item) for item in n.elts]),
            (ast.Tuple, lambda n: tuple(self.evaluate(item) for item in n.elts)),
            (ast.Dict, lambda n: {self.evaluate(k): self.evaluate(v) for k, v in zip(n.keys, n.values)}),
        )
        for node_type, handler in handlers:
            if isinstance(node, node_type):
                return handler(node)

        raise V2ExpressionError(
            f"unsupported AST node '{type(node).__name__}' in expression '{self._expression}'"
        )

    def _eval_name(self, node: ast.Name) -> Any:
        if node.id == "true":
            return True
        if node.id == "false":
            return False
        if node.id == "null":
            return None
        if node.id in _EXPLICIT_ROOT_NAMESPACES or node.id == "bindings":
            return _get_from_context(self._context, node.id)
        if node.id in _context_keys(self._context):
            return _get_from_context(self._context, node.id)
        return resolve_name(node.id, self._context)

    def _eval_bool_op(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = self.evaluate(value)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value in node.values:
                result = self.evaluate(value)
                if result:
                    return result
            return result
        raise V2ExpressionError(f"unsupported boolean operator in '{self._expression}'")

    def _eval_unary_op(self, node: ast.UnaryOp) -> Any:
        operand = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub) and isinstance(operand, (int, float)):
            return -operand
        raise V2ExpressionError(f"unsupported unary operator in '{self._expression}'")

    def _eval_compare(self, node: ast.Compare) -> bool:
        left = self.evaluate(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.evaluate(comp)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            else:
                raise V2ExpressionError(f"unsupported comparison operator in '{self._expression}'")
            if not ok:
                return False
            left = right
        return True

    def _eval_attribute(self, node: ast.Attribute) -> Any:
        base = self.evaluate(node.value)
        return _get_member(base, node.attr)

    def _eval_subscript(self, node: ast.Subscript) -> Any:
        base = self.evaluate(node.value)
        if isinstance(node.slice, ast.Slice):
            raise V2ExpressionError(f"slice access is not allowed in '{self._expression}'")
        key = self.evaluate(node.slice)
        return _get_index(base, key)

    def _eval_call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise V2ExpressionError(f"only direct function names are allowed in '{self._expression}'")
        if node.keywords:
            raise V2ExpressionError(f"keyword arguments are not allowed in '{self._expression}'")

        fn_name = node.func.id
        args = [self.evaluate(arg) for arg in node.args]

        if fn_name == "len":
            if len(args) != 1:
                raise V2ExpressionError("len() expects exactly one argument")
            return len(args[0])
        if fn_name == "empty":
            if len(args) != 1:
                raise V2ExpressionError("empty() expects exactly one argument")
            return _is_empty(args[0])
        if fn_name == "exists":
            if len(args) != 1:
                raise V2ExpressionError("exists() expects exactly one argument")
            return _exists(args[0])

        raise V2ExpressionError(
            f"function '{fn_name}' is not allowed in expression '{self._expression}'"
        )


def _unwrap_expr(expr: str) -> str:
    value = expr.strip()
    if value.startswith("${") and value.endswith("}"):
        return value[2:-1].strip()
    return value



def _context_keys(context: Mapping[str, Any] | Any) -> set[str]:
    if isinstance(context, Mapping):
        return {str(key) for key in context.keys()}
    try:
        return {name for name in dir(context) if not name.startswith("_")}
    except TypeError:
        return set()

def _get_from_context(context: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(context, Mapping):
        if key not in context:
            raise V2ExpressionError(f"namespace '{key}' is missing in context")
        return context[key]
    try:
        return getattr(context, key)
    except AttributeError as exc:
        raise V2ExpressionError(f"namespace '{key}' is missing in context") from exc


def _resolve_path(base: Any, remainder: str, original: str) -> Any:
    current = base
    index = 0
    while index < len(remainder):
        if remainder[index] == ".":
            index += 1
            continue
        if remainder[index] == "[":
            end = remainder.find("]", index)
            if end == -1:
                raise V2ExpressionError(f"invalid index path in '{original}'")
            token = remainder[index + 1 : end].strip()
            key = _parse_index_token(token, original)
            current = _get_index(current, key)
            index = end + 1
            continue

        token, index = _read_identifier(remainder, index)
        if not token:
            raise V2ExpressionError(f"invalid dotted path in '{original}'")
        current = _get_member(current, token)
    return current


def _parse_index_token(token: str, original: str) -> Any:
    if not token:
        raise V2ExpressionError(f"empty index in '{original}'")
    if token.startswith(("'", '"')) and token.endswith(("'", '"')) and len(token) >= 2:
        return token[1:-1]
    try:
        return int(token)
    except ValueError as exc:
        raise V2ExpressionError(f"unsupported index '{token}' in '{original}'") from exc


def _get_member(value: Any, name: str) -> Any:
    if name.startswith("_"):
        raise V2ExpressionError(f"access to private attribute '{name}' is not allowed")
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        raise V2ExpressionError(f"name '{name}' is not present in mapping")

    if is_dataclass(value):
        data = getattr(value, "__dict__", None)
        if isinstance(data, dict) and name in data:
            return data[name]

    try:
        return getattr(value, name)
    except AttributeError as exc:
        raise V2ExpressionError(f"attribute '{name}' is not available") from exc


def _get_index(value: Any, key: Any) -> Any:
    try:
        return value[key]
    except Exception as exc:  # noqa: BLE001
        raise V2ExpressionError(f"cannot index value with key {key!r}") from exc


def _split_reference(value: str) -> tuple[str, str]:
    idx = 0
    while idx < len(value) and (value[idx].isalnum() or value[idx] == "_"):
        idx += 1
    return value[:idx], value[idx:]


def _read_identifier(value: str, start: int) -> tuple[str, int]:
    idx = start
    if idx >= len(value) or not (value[idx].isalpha() or value[idx] == "_"):
        return "", start
    idx += 1
    while idx < len(value) and (value[idx].isalnum() or value[idx] == "_"):
        idx += 1
    return value[start:idx], idx



def _extract_locals_from_expr(expression: str) -> set[str]:
    refs: set[str] = set()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return refs

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr.startswith("_"):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "locals":
            refs.add(node.attr)
    return refs


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        return len(value) == 0
    except TypeError:
        return False


def _exists(value: Any) -> bool:
    if value is None:
        return False
    return Path(value).exists()
