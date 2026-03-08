"""Structural validation for YAML CLI UI v2 documents."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .errors import V2ValidationError
from .models import CommandDef, ForeachSpec, LauncherDef, OnErrorSpec, PipelineDef, StepSpec, V2Document

_LOCALS_REF_RE = re.compile(r"\$(?:\{locals\.([A-Za-z_][\w]*)\}|locals\.([A-Za-z_][\w]*))")


def validate_v2_document(doc: V2Document) -> None:
    """Validate v2-lite schema invariants required for step 4."""

    _validate_document(doc, is_root=True)


def _validate_document(doc: V2Document, *, is_root: bool) -> None:
    _validate_version(doc)
    _validate_callable_namespace(doc)
    _validate_locals_ordering(doc)
    _validate_profiles(doc)
    _validate_params(doc)
    _validate_commands(doc)
    _validate_pipelines(doc)
    _validate_launchers(doc)
    _validate_root_launchers(doc, is_root=is_root)
    _validate_imported_documents(doc)


def _validate_version(doc: V2Document) -> None:
    if doc.version != 2:
        raise V2ValidationError(
            f"unsupported v2 document version: {doc.version!r}; expected 2"
        )


def _validate_root_launchers(doc: V2Document, *, is_root: bool) -> None:
    if is_root and not doc.launchers:
        raise V2ValidationError("root v2 document must contain non-empty 'launchers'")


def _validate_imported_documents(doc: V2Document) -> None:
    for alias, imported in doc.imported_documents.items():
        if imported.profiles:
            raise V2ValidationError(
                f"imported document '{alias}' ({imported.source_path}) must not define profiles"
            )
        if imported.launchers:
            raise V2ValidationError(
                f"imported document '{alias}' ({imported.source_path}) must not define launchers"
            )
        _validate_document(imported, is_root=False)


def _validate_callable_namespace(doc: V2Document) -> None:
    conflicts = set(doc.commands).intersection(doc.pipelines)
    if conflicts:
        conflict_list = ", ".join(sorted(conflicts))
        raise V2ValidationError(
            f"command/pipeline name conflict in {doc.source_path}: {conflict_list}"
        )


def _extract_local_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        for m in _LOCALS_REF_RE.finditer(value):
            refs.add(m.group(1) or m.group(2))
    elif isinstance(value, dict):
        for nested_value in value.values():
            refs.update(_extract_local_refs(nested_value))
    elif isinstance(value, list):
        for nested_value in value:
            refs.update(_extract_local_refs(nested_value))
    return refs


def _validate_locals_ordering(doc: V2Document) -> None:
    seen: set[str] = set()
    for name, value in doc.locals.items():
        refs = _extract_local_refs(value)
        future = sorted(ref for ref in refs if ref != name and ref not in seen)
        if future:
            refs_list = ", ".join(future)
            raise V2ValidationError(
                f"local '{name}' in {doc.source_path} references future locals: {refs_list}"
            )
        seen.add(name)


def _validate_commands(doc: V2Document) -> None:
    for name, command in doc.commands.items():
        if not isinstance(command, CommandDef):
            raise V2ValidationError(f"commands.{name} must be CommandDef in {doc.source_path}")
        if command.run is None:
            raise V2ValidationError(f"commands.{name}.run is required in {doc.source_path}")
        if not command.run.program:
            raise V2ValidationError(
                f"commands.{name}.run.program must be non-empty in {doc.source_path}"
            )
        if not isinstance(command.run.argv, list):
            raise V2ValidationError(
                f"commands.{name}.run.argv must be a list in {doc.source_path}"
            )
        _validate_on_error(command.on_error, owner=f"commands.{name}", source=doc.source_path)


def _validate_pipelines(doc: V2Document) -> None:
    for name, pipeline in doc.pipelines.items():
        if not isinstance(pipeline, PipelineDef):
            raise V2ValidationError(f"pipelines.{name} must be PipelineDef in {doc.source_path}")
        if not isinstance(pipeline.steps, list):
            raise V2ValidationError(f"pipelines.{name}.steps must be a list in {doc.source_path}")
        _validate_steps(pipeline.steps, owner=f"pipelines.{name}", source=doc.source_path)
        _validate_on_error(pipeline.on_error, owner=f"pipelines.{name}", source=doc.source_path)


def _validate_launchers(doc: V2Document) -> None:
    for name, launcher in doc.launchers.items():
        if not isinstance(launcher, LauncherDef):
            raise V2ValidationError(f"launchers.{name} must be LauncherDef in {doc.source_path}")
        if not isinstance(launcher.title, str) or not launcher.title.strip():
            raise V2ValidationError(f"launchers.{name}.title must be non-empty in {doc.source_path}")
        if not isinstance(launcher.use, str) or not launcher.use.strip():
            raise V2ValidationError(f"launchers.{name}.use must be non-empty in {doc.source_path}")


def _validate_steps(steps: Iterable[StepSpec | str], *, owner: str, source: object) -> None:
    for index, step in enumerate(steps):
        _validate_step(step, owner=f"{owner}.steps[{index}]", source=source)


def _validate_step(step: StepSpec | str, *, owner: str, source: object) -> None:
    if isinstance(step, str):
        if not step.strip():
            raise V2ValidationError(f"{owner} must not be empty in {source}")
        return
    if not isinstance(step, StepSpec):
        raise V2ValidationError(f"{owner} must be string or StepSpec in {source}")

    has_use = isinstance(step.use, str) and bool(step.use.strip())
    has_foreach = step.foreach is not None
    if has_use == has_foreach:
        raise V2ValidationError(f"{owner} must contain exactly one of 'use' or 'foreach' in {source}")

    if step.step is not None and (not isinstance(step.step, str) or not step.step.strip()):
        raise V2ValidationError(f"{owner}.step must be a non-empty string in {source}")

    if step.with_values is not None and not isinstance(step.with_values, dict):
        raise V2ValidationError(f"{owner}.with must be a mapping in {source}")

    if step.foreach is not None:
        _validate_foreach(step.foreach, owner=owner, source=source)


def _validate_foreach(foreach: ForeachSpec, *, owner: str, source: object) -> None:
    if foreach.in_expr is None:
        raise V2ValidationError(f"{owner}.foreach.in is required in {source}")
    if not isinstance(foreach.as_name, str) or not foreach.as_name.strip():
        raise V2ValidationError(f"{owner}.foreach.as must be non-empty in {source}")
    if not isinstance(foreach.steps, list) or not foreach.steps:
        raise V2ValidationError(f"{owner}.foreach.steps must be a non-empty list in {source}")
    _validate_steps(foreach.steps, owner=f"{owner}.foreach", source=source)


def _validate_on_error(on_error: OnErrorSpec | None, *, owner: str, source: object) -> None:
    if on_error is None:
        return
    if not isinstance(on_error.steps, list) or not on_error.steps:
        raise V2ValidationError(f"{owner}.on_error.steps must be a non-empty list in {source}")
    _validate_steps(on_error.steps, owner=f"{owner}.on_error", source=source)


def _validate_profiles(_doc: V2Document) -> None:
    """Reserved for profile schema details on future steps."""


def _validate_params(_doc: V2Document) -> None:
    """Reserved for param schema details on future steps."""
