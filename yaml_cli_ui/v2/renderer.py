"""Template rendering helpers for YAML CLI UI v2."""

from __future__ import annotations

from typing import Any, Mapping

from .errors import V2ExpressionError
from .expr import evaluate_expression


def render_value(value: Any, context: Mapping[str, Any] | Any) -> Any:
    """Render scalar/list/mapping values with v2 template semantics."""

    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return render_scalar_or_ref(value, context)


def render_scalar_or_ref(value: Any, context: Mapping[str, Any] | Any) -> Any:
    """Render scalar value preserving native types for full-reference strings."""

    if not isinstance(value, str):
        return value

    text = value.strip()
    if text.startswith("$") and not text.startswith("${") and not text.startswith("$$") and _is_full_ref(text):
        expr = text[1:]
        return evaluate_expression(expr, context)

    return render_string(value, context)


def render_string(template: str, context: Mapping[str, Any] | Any) -> str:
    """Render a template string supporting $name, ${expr}, $$ and $${ escapes."""

    out: list[str] = []
    i = 0
    length = len(template)

    while i < length:
        if template.startswith("$${", i):
            out.append("${")
            i += 3
            continue
        if template.startswith("$$", i):
            out.append("$")
            i += 2
            continue
        if template.startswith("${", i):
            end = _find_closing_brace(template, i + 2)
            expr = template[i + 2 : end]
            out.append(_stringify_value(evaluate_expression(expr, context)))
            i = end + 1
            continue
        if template[i] == "$":
            name, next_index = _read_ref_token(template, i + 1)
            if name:
                out.append(_stringify_value(evaluate_expression(name, context)))
                i = next_index
                continue
        out.append(template[i])
        i += 1

    return "".join(out)


def _is_full_ref(value: str) -> bool:
    name, index = _read_ref_token(value, 1)
    return bool(name) and index == len(value)


def _read_ref_token(value: str, start: int) -> tuple[str, int]:
    i = start
    if i >= len(value) or not (value[i].isalpha() or value[i] == "_"):
        return "", start
    i += 1
    while i < len(value):
        char = value[i]
        if char.isalnum() or char == "_":
            i += 1
            continue
        if char == ".":
            i += 1
            if i >= len(value) or not (value[i].isalpha() or value[i] == "_"):
                return "", start
            i += 1
            continue
        if char == "[":
            close = value.find("]", i)
            if close == -1:
                return "", start
            i = close + 1
            continue
        break
    return value[start:i], i


def _find_closing_brace(value: str, start: int) -> int:
    depth = 1
    i = start
    in_string: str | None = None

    while i < len(value):
        char = value[i]
        if in_string:
            if char == "\\":
                i += 2
                continue
            if char == in_string:
                in_string = None
            i += 1
            continue

        if char in {'"', "'"}:
            in_string = char
            i += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1

    raise V2ExpressionError(f"unterminated template expression in '{value}'")


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
