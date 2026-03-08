"""argv DSL serializer for YAML CLI UI v2.

EBNF (v2 step-7 subset)
-----------------------
Argv := [ArgvItem, ...]
ArgvItem := ScalarItem | OptionMap | ConditionalItem
ScalarItem := string | number | boolean | "$name" | "${expr}" inside string
OptionMap := { option_name : value }
ConditionalItem := { "when": value_or_expr, "then": ArgvItem }

Serialization rules:
- Scalar item -> exactly one argv token (stringified, no shell splitting)
- Option map -> zero/one/many tokens depending on value semantics
- Conditional item -> serialize nested item only when `when` is truthy
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import V2ExecutionError, V2ValidationError
from .renderer import render_scalar_or_ref, render_value

_RESERVED_CONDITIONAL_KEYS = {"when", "then"}


def is_option_map(item: Any) -> bool:
    """Return True when item is a one-key option map ({--flag: value})."""

    if not isinstance(item, Mapping) or len(item) != 1:
        return False
    key = next(iter(item.keys()))
    return isinstance(key, str) and key not in _RESERVED_CONDITIONAL_KEYS


def is_conditional_item(item: Any) -> bool:
    """Return True when item shape is exactly {when: ..., then: ...}."""

    return isinstance(item, Mapping) and set(item.keys()) == _RESERVED_CONDITIONAL_KEYS


def serialize_argv(argv_items: list[Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize a v2 argv DSL list into subprocess argv tokens."""

    if not isinstance(argv_items, list):
        raise V2ValidationError("argv must be a list")

    result: list[str] = []
    for item in argv_items:
        result.extend(serialize_argv_item(item, context))
    return result


def serialize_argv_item(item: Any, context: Mapping[str, Any]) -> list[str]:
    """Serialize one argv item according to supported DSL shapes."""

    if is_conditional_item(item):
        return serialize_conditional_item(item, context)
    if is_option_map(item):
        return serialize_option_map(item, context)
    if isinstance(item, Mapping):
        raise V2ValidationError(
            "Invalid argv map shape: expected exactly one option key or exactly {'when', 'then'}"
        )
    return [_serialize_scalar_item(item, context)]


def serialize_option_map(item: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize option map item `{option: value}`."""

    option_name, raw_value = next(iter(item.items()))
    if not isinstance(option_name, str) or not option_name:
        raise V2ValidationError("Option map key must be a non-empty string")

    rendered = render_value(raw_value, context)

    if rendered is True:
        return [option_name]
    if rendered is False or rendered is None:
        return []
    if rendered == "":
        return []

    if isinstance(rendered, list):
        tokens: list[str] = []
        for value in rendered:
            tokens.extend([option_name, _stringify_scalar(value, "Option map list value")])
        return tokens

    if isinstance(rendered, Mapping):
        raise V2ExecutionError("Option map value resolved to mapping; expected scalar/list")

    return [option_name, _stringify_scalar(rendered, "Option map value")]


def serialize_conditional_item(item: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Serialize conditional item `{when: ..., then: ...}`."""

    when_value = render_scalar_or_ref(item["when"], context)
    if not bool(when_value):
        return []

    then_item = item["then"]
    if is_conditional_item(then_item):
        raise V2ValidationError("Conditional 'then' does not support nested conditional item in v2 step-7")
    return serialize_argv_item(then_item, context)


def _serialize_scalar_item(item: Any, context: Mapping[str, Any]) -> str:
    rendered = render_scalar_or_ref(item, context)

    if rendered is None:
        raise V2ExecutionError("Standalone scalar argv item resolved to None")
    if isinstance(rendered, (list, Mapping, tuple, set)):
        raise V2ExecutionError("Scalar argv item resolved to a non-scalar value")

    return _stringify_scalar(rendered, "Scalar argv item")


def _stringify_scalar(value: Any, label: str) -> str:
    if isinstance(value, (list, Mapping, tuple, set)):
        raise V2ExecutionError(f"{label} must be scalar")
    if value is None:
        raise V2ExecutionError(f"{label} resolved to None")
    return str(value)
