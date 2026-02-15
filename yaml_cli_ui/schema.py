from __future__ import annotations

from typing import Any


class SchemaError(ValueError):
    pass


def validate_workflow(doc: dict[str, Any]) -> None:
    if not isinstance(doc, dict):
        raise SchemaError("Root YAML must be a map")
    if doc.get("version") != 1:
        raise SchemaError("Only version: 1 is supported")
    actions = doc.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise SchemaError("actions must be a non-empty mapping")
    for action_id, action in actions.items():
        if not isinstance(action, dict):
            raise SchemaError(f"Action '{action_id}' must be a map")
        if not action.get("title"):
            raise SchemaError(f"Action '{action_id}' requires title")
        if "pipeline" not in action and "run" not in action:
            raise SchemaError(f"Action '{action_id}' requires pipeline or run")
        if "pipeline" in action and not isinstance(action["pipeline"], list):
            raise SchemaError(f"Action '{action_id}'.pipeline must be list")
        if "form" in action:
            form = action["form"]
            if not isinstance(form, dict):
                raise SchemaError(f"Action '{action_id}'.form must be map")
            fields = form.get("fields", [])
            if not isinstance(fields, list):
                raise SchemaError(f"Action '{action_id}'.form.fields must be list")
            for field in fields:
                if not isinstance(field, dict) or "id" not in field or "type" not in field:
                    raise SchemaError(f"Action '{action_id}' has invalid form field")
