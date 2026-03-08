"""Safe expression evaluation for YAML CLI UI v2."""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .errors import V2ExpressionError

_ALLOWED_NAMESPACES = ("params", "locals", "profile", "steps", "run", "loop", "error")
_LOCAL_REF_RE = re.compile(r"\$locals\.([A-Za-z_][A-Za-z0-9_]*)|\$\{locals\.([A-Za-z_][A-Za-z0-9_]*)\}")
_FULL_EXPR_RE = re.compile(r"^\$\{(?P<expr>.*)\}$", re.DOTALL)


def evaluate_expression(expr: str, context: Mapping[str, Any]) -> Any:
    """Evaluate a safe v2 expression against context."""

    normalized = _normalize_expression(expr)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise V2ExpressionError(f"Invalid expression syntax: {expr!r}") from exc
    evaluator = _SafeEvaluator(context=context, raw_expression=expr)
    return evaluator.eval(tree)


def resolve_name(name: str, context: Mapping[str, Any]) -> Any:
    """Resolve short or namespaced name from context."""

    if not name or not isinstance(name, str):
        raise V2ExpressionError(f"Invalid name reference: {name!r}")

    if name in _ALLOWED_NAMESPACES:
        root = _try_get_context_root(context, name)
        if root is not _MISSING:
            return root

    parts = name.split(".")
    if len(parts) > 1:
        namespace = parts[0]
        if namespace not in _ALLOWED_NAMESPACES:
            raise V2ExpressionError(f"Unknown namespace in name reference: {name!r}")
        root = _get_context_root(context, namespace, name)
        return resolve_dotted_path(root, parts[1:], origin=name)

    hits: list[tuple[str, Any]] = []
    for namespace in _ALLOWED_NAMESPACES:
        root = _try_get_context_root(context, namespace)
        if root is _MISSING:
            continue
        member = _try_get_member(root, name)
        if member is not _MISSING:
            hits.append((namespace, member))

    if not hits:
        raise V2ExpressionError(f"Unknown name reference: {name!r}")
    if len(hits) > 1:
        spaces = ", ".join(sorted(namespace for namespace, _ in hits))
        raise V2ExpressionError(f"Ambiguous short name reference: {name!r}; matches namespaces: {spaces}")
    return hits[0][1]


def resolve_dotted_path(root: Any, parts: list[str], *, origin: str) -> Any:
    """Resolve dotted path segments over dict-like/object-like values."""

    current = root
    for part in parts:
        current = _get_member(current, part, origin)
    return current


def extract_local_refs(value: str) -> set[str]:
    """Extract refs to locals from a string template/expression."""

    if not isinstance(value, str):
        return set()
    refs: set[str] = set()
    for match in _LOCAL_REF_RE.finditer(value):
        refs.add(match.group(1) or match.group(2))
    return refs


def _normalize_expression(expr: str) -> str:
    if not isinstance(expr, str):
        raise V2ExpressionError(f"Expression must be string, got: {type(expr).__name__}")
    stripped = expr.strip()
    match = _FULL_EXPR_RE.match(stripped)
    if match:
        return match.group("expr").strip()
    return stripped


def _get_context_root(context: Mapping[str, Any], namespace: str, source: str) -> Any:
    value = _try_get_context_root(context, namespace)
    if value is _MISSING:
        raise V2ExpressionError(f"Unknown context namespace while resolving {source!r}: {namespace!r}")
    return value


def _try_get_context_root(context: Mapping[str, Any], namespace: str) -> Any:
    if isinstance(context, Mapping):
        return context.get(namespace, _MISSING)
    return getattr(context, namespace, _MISSING)


def _get_member(container: Any, key: str, origin: str) -> Any:
    value = _try_get_member(container, key)
    if value is _MISSING:
        raise V2ExpressionError(f"Unable to resolve path {origin!r}: missing {key!r}")
    return value


def _try_get_member(container: Any, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key, _MISSING)
    if is_dataclass(container):
        data = asdict(container)
        return data.get(key, _MISSING)
    return getattr(container, key, _MISSING)


def _fn_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        return len(value) == 0
    except TypeError:
        return False


def _fn_exists(value: Any) -> bool:
    if value is None:
        return False
    return os.path.exists(os.fspath(value))


_MISSING = object()


class _SafeEvaluator:
    def __init__(self, *, context: Mapping[str, Any], raw_expression: str) -> None:
        self.context = context
        self.raw_expression = raw_expression

    def eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self.eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "true":
                return True
            if node.id == "false":
                return False
            if node.id == "null":
                return None
            return resolve_name(node.id, self.context)
        if isinstance(node, ast.Attribute):
            base = self.eval(node.value)
            return _get_member(base, node.attr, self.raw_expression)
        if isinstance(node, ast.Subscript):
            container = self.eval(node.value)
            if isinstance(node.slice, ast.Slice):
                raise V2ExpressionError(f"Slices are not supported in expression: {self.raw_expression!r}")
            index = self.eval(node.slice)
            try:
                return container[index]
            except Exception as exc:  # noqa: BLE001
                raise V2ExpressionError(
                    f"Index access failed in expression {self.raw_expression!r}: [{index!r}]"
                ) from exc
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self.eval(node.operand)
        if isinstance(node, ast.BoolOp):
            return self._eval_boolop(node)
        if isinstance(node, ast.Compare):
            return self._eval_compare(node)
        if isinstance(node, ast.List):
            return [self.eval(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self.eval(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return {self.eval(k): self.eval(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Call):
            return self._eval_call(node)

        raise V2ExpressionError(
            f"Unsupported AST node in expression {self.raw_expression!r}: {type(node).__name__}"
        )

    def _eval_boolop(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result = True
            for value_node in node.values:
                result = self.eval(value_node)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value_node in node.values:
                result = self.eval(value_node)
                if result:
                    return result
            return result
        raise V2ExpressionError(f"Unsupported boolean operator in expression: {self.raw_expression!r}")

    def _eval_compare(self, node: ast.Compare) -> bool:
        left = self.eval(node.left)
        for op, comparator_node in zip(node.ops, node.comparators):
            right = self.eval(comparator_node)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            else:
                raise V2ExpressionError(
                    f"Unsupported comparison operator in expression {self.raw_expression!r}: {type(op).__name__}"
                )
            if not ok:
                return False
            left = right
        return True

    def _eval_call(self, node: ast.Call) -> Any:
        if node.keywords:
            raise V2ExpressionError(f"Keyword args are not allowed in expression: {self.raw_expression!r}")
        if not isinstance(node.func, ast.Name):
            raise V2ExpressionError(f"Only direct function names are allowed in expression: {self.raw_expression!r}")

        name = node.func.id
        args = [self.eval(arg) for arg in node.args]
        if len(args) != 1:
            raise V2ExpressionError(f"Function {name!r} expects exactly one argument")

        if name == "len":
            return len(args[0])
        if name == "empty":
            return _fn_empty(args[0])
        if name == "exists":
            return _fn_exists(args[0])
        raise V2ExpressionError(f"Function is not allowed in expression: {name!r}")
