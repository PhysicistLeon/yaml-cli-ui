"""Runtime context and locals evaluation helpers for YAML CLI UI v2.

EBNF sketch for this module:

    LocalEvaluation := LocalDef*
    LocalDef := local_name ":" Value

    Rule :=
      each local may reference only:
        params
        profile
        earlier locals
        imported namespace locals
        run

    Context := RootNamespaces + ImportedNamespaces + WithBindings + OptionalLoop + OptionalError
    RootNamespaces := params + locals + profile + run + steps
    ImportedNamespaces := { alias -> { locals: ... } }
    ShortNameResolution := unique(with_values ∪ params ∪ locals ∪ run ∪ loop ∪ error)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .errors import V2ExecutionError
from .models import RunContext, V2Document
from .renderer import render_value


def resolve_selected_profile(
    doc: V2Document,
    selected_profile_name: str | None = None,
    selected_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve profile used for runtime context assembly."""

    if selected_profile is not None:
        return dict(selected_profile)

    profiles = doc.profiles or {}
    if selected_profile_name is not None:
        profile_def = profiles.get(selected_profile_name)
        if profile_def is None:
            raise V2ExecutionError(f"unknown profile '{selected_profile_name}'")
        return _to_plain_mapping(profile_def)

    if not profiles:
        return {}

    if len(profiles) == 1:
        _, profile_def = next(iter(profiles.items()))
        return _to_plain_mapping(profile_def)

    available = ", ".join(sorted(profiles.keys()))
    raise V2ExecutionError(
        f"multiple profiles are defined; select one explicitly: {available}"
    )


def build_base_context(
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
    steps: Mapping[str, Any] | None = None,
    imported_locals: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build base explicit-namespace context used by renderer/evaluator."""

    context: dict[str, Any] = {
        "params": dict(params),
        "locals": {},
        "profile": dict(selected_profile or {}),
        "run": dict(run or {}),
        "steps": dict(steps or {}),
    }
    if imported_locals:
        for alias, values in imported_locals.items():
            context[alias] = {"locals": dict(values)}
    return context


def merge_with_bindings(
    context: Mapping[str, Any], with_values: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Merge short-name bindings for expression resolver.

    Explicit namespaces remain unchanged. Bindings are exposed via dedicated
    `bindings` bucket and should not overwrite `params`, `locals`, etc.
    """

    merged = dict(context)
    merged["bindings"] = dict(with_values or {})
    return merged


def evaluate_root_locals(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
    imported_locals: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate root locals top-to-bottom with restricted runtime visibility."""

    return _evaluate_document_locals(
        doc,
        params=params,
        selected_profile=selected_profile,
        run=run,
        imported_locals=imported_locals,
    )


def build_runtime_context(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile_name: str | None = None,
    selected_profile: Mapping[str, Any] | None = None,
    run: Mapping[str, Any] | None = None,
    steps: Mapping[str, Any] | None = None,
    loop: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    with_values: Mapping[str, Any] | None = None,
) -> RunContext:
    """Assemble v2 runtime context with eager imported/root locals evaluation."""

    profile = resolve_selected_profile(
        doc,
        selected_profile_name=selected_profile_name,
        selected_profile=selected_profile,
    )
    run_values = dict(run or {})

    imported = build_imported_locals_context(
        doc,
        params=params,
        selected_profile=profile,
        run=run_values,
    )
    root_locals = evaluate_root_locals(
        doc,
        params=params,
        selected_profile=profile,
        run=run_values,
        imported_locals=imported,
    )

    return RunContext(
        params=dict(params),
        locals=root_locals,
        profile=profile,
        run=run_values,
        steps=dict(steps or {}),
        loop=dict(loop) if loop is not None else None,
        error=dict(error) if error is not None else None,
        imported=imported or None,
        bindings=dict(with_values or {}),
    )


def build_imported_locals_context(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Evaluate locals for each imported namespace alias."""

    result: dict[str, dict[str, Any]] = {}
    for alias, imported_doc in doc.imported_documents.items():
        result[alias] = evaluate_imported_document_locals(
            imported_doc,
            params=params,
            selected_profile=selected_profile,
            run=run,
        )
    return result


def evaluate_imported_document_locals(
    imported_doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate locals for imported document with recursive imports support."""

    nested_imported = build_imported_locals_context(
        imported_doc,
        params=params,
        selected_profile=selected_profile,
        run=run,
    )
    return _evaluate_document_locals(
        imported_doc,
        params=params,
        selected_profile=selected_profile,
        run=run,
        imported_locals=nested_imported,
    )


def context_to_mapping(run_context: RunContext) -> dict[str, Any]:
    """Convert :class:`RunContext` into evaluator/renderer mapping."""

    return run_context.as_mapping()


def _evaluate_document_locals(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None,
    imported_locals: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    profile = dict(selected_profile or {})
    run_values = dict(run or {})
    imported = {alias: dict(values) for alias, values in (imported_locals or {}).items()}

    evaluated: dict[str, Any] = {}
    for local_name, local_value in doc.locals.items():
        local_context = {
            "params": dict(params),
            "profile": profile,
            "locals": evaluated,
            "run": run_values,
            "bindings": {},
        }
        for alias, values in imported.items():
            local_context[alias] = {"locals": values}

        try:
            evaluated[local_name] = render_value(local_value, local_context)
        except Exception as exc:  # noqa: BLE001
            raise V2ExecutionError(
                f"failed to evaluate local '{local_name}' in {doc.source_path}: {exc}"
            ) from exc

    return evaluated


def _to_plain_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    raise V2ExecutionError(
        f"profile value must be a mapping-like object, got {type(value).__name__}"
    )
