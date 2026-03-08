"""Internal template parsing helpers for v2 expression/renderer."""

from __future__ import annotations

from .errors import V2ExpressionError


def find_closing_brace(value: str, start: int) -> int:
    """Find matching closing brace for a `${...}` expression starting at `start`."""

    depth = 1
    index = start
    in_string: str | None = None
    while index < len(value):
        char = value[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = None
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1

    raise V2ExpressionError(f"unterminated template expression in '{value}'")
