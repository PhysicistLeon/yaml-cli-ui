"""Document validation scaffold for YAML CLI UI v2."""

from __future__ import annotations

from .errors import V2ValidationError
from .models import V2Document


def validate_v2_document(doc: V2Document) -> None:
    """Validate minimal, safe invariants for v2 document scaffold."""

    _validate_version(doc)
    _validate_required_sections(doc)
    _validate_name_conflicts(doc)
    _validate_callable_namespace(doc)
    _validate_launchers_shape(doc)
    _validate_commands_and_pipelines_shape(doc)


def _validate_version(doc: V2Document) -> None:
    if doc.version != 2:
        raise V2ValidationError(
            f"unsupported v2 document version: {doc.version!r}; expected 2"
        )


def _validate_required_sections(doc: V2Document) -> None:
    launchers = doc.raw.get("launchers")
    if launchers is None:
        raise V2ValidationError("v2 document must contain top-level 'launchers' section")
    if not isinstance(launchers, dict) or not launchers:
        raise V2ValidationError("v2 document field 'launchers' must be a non-empty mapping")


def _validate_name_conflicts(_doc: V2Document) -> None:
    """Reserved for future checks of conflicts across callables/import aliases."""


def _validate_callable_namespace(_doc: V2Document) -> None:
    """Reserved for future callable namespace checks (commands/pipelines/imports)."""


def _validate_launchers_shape(_doc: V2Document) -> None:
    """Reserved for detailed launcher schema checks."""


def _validate_commands_and_pipelines_shape(_doc: V2Document) -> None:
    """Reserved for command/pipeline structure checks."""
