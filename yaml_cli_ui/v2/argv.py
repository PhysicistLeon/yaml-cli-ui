"""Argv DSL serializer for YAML CLI UI v2.

EBNF (minimal):

Argv := [ArgvItem, ...]
ArgvItem := ScalarItem | OptionMap | ConditionalItem
ScalarItem := string | number | boolean | "$name" | "${expr}" inside string
OptionMap := { option_name: value }
ConditionalItem := { "when": value_or_expr, "then": ArgvItem }

Serialization rules:
- scalar -> one argv token (no shell splitting)
- option map -> zero/one/many tokens depending on rendered value
- conditional -> serialize nested item only when rendered `when` is truthy
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import V2ExecutionError, V2ValidationError
from .renderer import render_scalar_or_ref, render_value

_RESERVED_KEYS = {"when", "then"}


def is_option_map(item: Any) -> bool:
    """Return True when item is an option map: exactly one non-reserved key."""

    if not isinstance(item, Mapping) or len(item) != 1:
        return False
    key = next(iter(item.keys()))
    return key not in _RESERVED_KEYS


def is_conditional_item(item: Any) -> bool:
    """Return True when item is exactly a {when, then} conditional map."""

    if not isinstance(item, Mapping):
        return False
    return set(item.keys()) == {"when", "then"}


def serialize_argv(argv_items: list[Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize v2 argv DSL into subprocess-ready argv tokens."""

    if not isinstance(argv_items, list):
        raise V2ValidationError("argv must be a list")

    serialized: list[str] = []
    for index, item in enumerate(argv_items):
        try:
            serialized.extend(serialize_argv_item(item, context))
        except (V2ValidationError, V2ExecutionError) as exc:
            raise type(exc)(f"argv[{index}]: {exc}") from exc
    return serialized


def serialize_argv_item(item: Any, context: Mapping[str, Any]) -> list[str]:
    """Serialize a single argv item into zero/one/many argv tokens."""

    if is_conditional_item(item):
        return serialize_conditional_item(item, context)
    if is_option_map(item):
        return serialize_option_map(item, context)
    if isinstance(item, Mapping):
        raise V2ValidationError(
            "Invalid argv item shape: dict item must be option map {--opt: value} "
            "or conditional item {when: ..., then: ...}"
        )
    return _serialize_scalar_item(item, context)


def serialize_option_map(item: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize option map {key: value}."""

    key, raw_value = next(iter(item.items()))
    if not isinstance(key, str) or key == "":
        raise V2ValidationError("Option map key must be a non-empty string")

    rendered = render_value(raw_value, context)

    if isinstance(rendered, bool):
        return [key] if rendered else []
    if rendered is None:
        return []
    if isinstance(rendered, str) and rendered == "":
        return []
    if isinstance(rendered, list):
        if not rendered:
            return []
        return _serialize_option_list_values(key, rendered)
    if isinstance(rendered, Mapping):
        raise V2ExecutionError(
            f"Option map value for '{key}' rendered to mapping, scalar/list expected"
        )
    return [key, str(rendered)]


def serialize_conditional_item(item: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize conditional item {when: ..., then: ...}."""

    when_value = render_scalar_or_ref(item["when"], context)
    if bool(when_value):
        return serialize_argv_item(item["then"], context)
    return []


def _serialize_scalar_item(item: Any, context: Mapping[str, Any]) -> list[str]:
    if item is None:
        raise V2ValidationError("Standalone argv scalar item must not be null")
    if isinstance(item, (list, tuple, set)):
        raise V2ValidationError("Standalone argv item must not be list-like")

    rendered = render_scalar_or_ref(item, context)
    if rendered is None:
        raise V2ExecutionError("Standalone argv scalar item rendered to null")
    if isinstance(rendered, (list, Mapping)):
        raise V2ExecutionError(
            "Standalone argv scalar item rendered to non-scalar value (list/dict)"
        )
    return [str(rendered)]


def _serialize_option_list_values(key: str, values: list[Any]) -> list[str]:
    tokens: list[str] = []
    for index, value in enumerate(values):
        if isinstance(value, (list, Mapping)):
            raise V2ExecutionError(
                f"Option list value at index {index} for '{key}' must be scalar"
            )
        tokens.extend([key, str(value)])
    return tokens


__all__ = [
    "serialize_argv",
    "serialize_argv_item",
    "serialize_option_map",
    "serialize_conditional_item",
    "is_option_map",
    "is_conditional_item",
]
