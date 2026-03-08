"""Template rendering for YAML CLI UI v2."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .errors import V2ExpressionError
from .expr import evaluate_expression, resolve_name

_FULL_REF_RE = re.compile(r"^\$(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$")


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """Render value using v2 scalar/reference semantics."""

    return render_scalar_or_ref(value, context)


def render_scalar_or_ref(value: Any, context: Mapping[str, Any]) -> Any:
    """Render scalar value preserving native type for full references."""

    if not isinstance(value, str):
        return value

    match = _FULL_REF_RE.match(value.strip())
    if match:
        return resolve_name(match.group("name"), context)

    stripped = value.strip()
    if stripped.startswith("${") and stripped.endswith("}") and stripped.count("${") == 1:
        return evaluate_expression(stripped, context)

    return render_string(value, context)


def render_string(template: str, context: Mapping[str, Any]) -> str:
    """Render template string with ${expr} interpolation and dollar escaping."""

    if not isinstance(template, str):
        raise V2ExpressionError(f"render_string expects str, got {type(template).__name__}")

    result: list[str] = []
    idx = 0
    while idx < len(template):
        if template.startswith("$${", idx):
            result.append("${")
            idx += 3
            continue
        if template.startswith("$$", idx):
            result.append("$")
            idx += 2
            continue
        if template.startswith("${", idx):
            end = template.find("}", idx + 2)
            if end == -1:
                raise V2ExpressionError(f"Unclosed '${{...}}' template expression: {template!r}")
            expr = template[idx + 2 : end].strip()
            value = evaluate_expression(expr, context)
            result.append("" if value is None else str(value))
            idx = end + 1
            continue
        result.append(template[idx])
        idx += 1

    return "".join(result)
