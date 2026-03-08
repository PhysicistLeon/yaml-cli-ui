"""Structural validator for YAML CLI UI v2-lite documents."""

from __future__ import annotations

from typing import Any

from .errors import V2ValidationError
from .expr import extract_local_refs
from .models import CommandDef, PipelineDef, StepSpec, V2Document

def validate_v2_document(doc: V2Document) -> None:
    """Validate structural invariants for a loaded v2 document."""

    _validate_version(doc)
    _validate_root_launchers(doc)
    _validate_imported_documents(doc)
    _validate_callable_namespace(doc)
    _validate_locals_ordering(doc)
    _validate_profiles(doc)
    _validate_params(doc)
    _validate_commands(doc)
    _validate_pipelines(doc)
    _validate_launchers(doc)


def _validate_version(doc: V2Document) -> None:
    if doc.version != 2:
        raise V2ValidationError(f"unsupported v2 document version: {doc.version!r}; expected 2")


def _validate_root_launchers(doc: V2Document) -> None:
    if not doc.launchers:
        raise V2ValidationError("V2E_ROOT_LAUNCHERS_REQUIRED: root v2 document must contain non-empty 'launchers'")


def _validate_imported_documents(doc: V2Document) -> None:
    for alias, imported in doc.imported_documents.items():
        if imported.profiles:
            raise V2ValidationError(
                f"V2E_IMPORTED_PROFILES_FORBIDDEN: imported document '{alias}' ({imported.source_path}) must not define 'profiles'"
            )
        if imported.launchers:
            raise V2ValidationError(
                f"V2E_IMPORTED_LAUNCHERS_FORBIDDEN: imported document '{alias}' ({imported.source_path}) must not define 'launchers'"
            )
        _validate_callable_namespace(imported)
        _validate_locals_ordering(imported)
        _validate_commands(imported)
        _validate_pipelines(imported)
        _validate_imported_documents(imported)


def _validate_callable_namespace(doc: V2Document) -> None:
    conflicts = sorted(set(doc.commands).intersection(doc.pipelines))
    if conflicts:
        names = ", ".join(conflicts)
        raise V2ValidationError(
            f"V2E_CALLABLE_NAMESPACE_CONFLICT: callable namespace conflict in {doc.source_path}: commands/pipelines duplicate names: {names}"
        )


def _extract_local_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        return extract_local_refs(value)
    if isinstance(value, dict):
        for key, item in value.items():
            refs.update(_extract_local_refs(key))
            refs.update(_extract_local_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_extract_local_refs(item))
    return refs


def _validate_locals_ordering(doc: V2Document) -> None:
    seen: set[str] = set()
    for name, value in doc.locals.items():
        refs = _extract_local_refs(value)
        unresolved = {ref for ref in refs if ref != name and ref not in seen}
        if unresolved:
            raise V2ValidationError(
                f"V2E_LOCALS_ORDERING: local '{name}' in {doc.source_path} references not-yet-defined locals: "
                f"{', '.join(sorted(unresolved))}"
            )
        seen.add(name)


def _validate_profiles(doc: V2Document) -> None:
    if not isinstance(doc.profiles, dict):
        raise V2ValidationError(f"profiles section must be mapping in {doc.source_path}")


def _validate_params(doc: V2Document) -> None:
    if not isinstance(doc.params, dict):
        raise V2ValidationError(f"params section must be mapping in {doc.source_path}")


def _validate_commands(doc: V2Document) -> None:
    for name, command in doc.commands.items():
        _validate_command(name, command, doc)


def _validate_command(name: str, command: CommandDef, doc: V2Document) -> None:
    if command.run is None:
        raise V2ValidationError(f"V2E_COMMAND_RUN_REQUIRED: command '{name}' in {doc.source_path} must define 'run'")
    if not isinstance(command.run.program, str) or not command.run.program.strip():
        raise V2ValidationError(f"command '{name}' in {doc.source_path} must define non-empty run.program")
    if not isinstance(command.run.argv, list):
        raise V2ValidationError(f"command '{name}' in {doc.source_path} must define run.argv as list")
    _validate_on_error(command.on_error, f"command '{name}'", doc)


def _validate_pipelines(doc: V2Document) -> None:
    for name, pipeline in doc.pipelines.items():
        _validate_pipeline(name, pipeline, doc)


def _validate_pipeline(name: str, pipeline: PipelineDef, doc: V2Document) -> None:
    if not isinstance(pipeline.steps, list):
        raise V2ValidationError(f"pipeline '{name}' in {doc.source_path} must define steps as list")
    _validate_steps(pipeline.steps, f"pipeline '{name}'", doc)
    _validate_on_error(pipeline.on_error, f"pipeline '{name}'", doc)


def _validate_steps(steps: list[StepSpec | str], owner: str, doc: V2Document) -> None:
    for idx, step in enumerate(steps):
        location = f"{owner} step #{idx}"
        if isinstance(step, str):
            continue
        if not isinstance(step, StepSpec):
            raise V2ValidationError(f"{location} in {doc.source_path} must be string or expanded step")

        has_use = step.use is not None
        has_foreach = step.foreach is not None
        if has_use == has_foreach:
            raise V2ValidationError(f"V2E_STEP_MODE_EXCLUSIVE: {location} in {doc.source_path} must define exactly one of use/foreach")

        if step.step is not None and (not isinstance(step.step, str) or not step.step.strip()):
            raise V2ValidationError(f"{location} in {doc.source_path} has invalid 'step' field")

        if step.with_values is not None and not isinstance(step.with_values, dict):
            raise V2ValidationError(f"{location} in {doc.source_path} has invalid 'with' field")

        if step.foreach is not None:
            _validate_foreach(step.foreach, location, doc)


def _validate_foreach(foreach: Any, owner: str, doc: V2Document) -> None:
    if foreach.in_expr is None:
        raise V2ValidationError(f"{owner} in {doc.source_path} missing foreach.in")
    if not isinstance(foreach.as_name, str) or not foreach.as_name.strip():
        raise V2ValidationError(f"V2E_FOREACH_AS_REQUIRED: {owner} in {doc.source_path} missing non-empty foreach.as")
    if not isinstance(foreach.steps, list) or not foreach.steps:
        raise V2ValidationError(f"{owner} in {doc.source_path} missing non-empty foreach.steps")
    _validate_steps(foreach.steps, f"{owner} foreach", doc)


def _validate_launchers(doc: V2Document) -> None:
    for name, launcher in doc.launchers.items():
        if not isinstance(launcher.title, str) or not launcher.title.strip():
            raise V2ValidationError(f"launcher '{name}' in {doc.source_path} must have non-empty title")
        if not isinstance(launcher.use, str) or not launcher.use.strip():
            raise V2ValidationError(f"launcher '{name}' in {doc.source_path} must have non-empty use")


def _validate_on_error(on_error: Any, owner: str, doc: V2Document) -> None:
    if on_error is None:
        return
    if not on_error.steps:
        raise V2ValidationError(f"{owner} in {doc.source_path} has empty on_error.steps")
    _validate_steps(on_error.steps, f"{owner} on_error", doc)
