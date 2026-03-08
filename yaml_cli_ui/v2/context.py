"""v2 runtime context and locals evaluation helpers.

EBNF (step 6 scope):
- LocalEvaluation := LocalDef*
- LocalDef := local_name ":" Value
- each local may reference only params/profile/earlier locals/imported ns.locals/run
- Context := RootNamespaces + ImportedNamespaces + WithBindings + OptionalLoop + OptionalError
- ShortNameResolution := unique(with_values ∪ params ∪ locals ∪ run ∪ loop ∪ error)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import V2ExecutionError
from .models import RunContext, V2Document
from .renderer import render_scalar_or_ref


ROOT_NAMESPACE_KEYS = ("params", "locals", "profile", "run", "steps")


def resolve_selected_profile(
    doc: V2Document,
    selected_profile_name: str | None = None,
    selected_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve effective profile mapping for runtime context."""

    if selected_profile is not None:
        return dict(selected_profile)

    if selected_profile_name is not None:
        profile_def = doc.profiles.get(selected_profile_name)
        if profile_def is None:
            raise V2ExecutionError(
                f"selected profile '{selected_profile_name}' is not defined"
            )
        return _profile_to_mapping(profile_def)

    if not doc.profiles:
        return {}

    if len(doc.profiles) == 1:
        (_, profile_def), = doc.profiles.items()
        return _profile_to_mapping(profile_def)

    raise V2ExecutionError(
        "profile selection is ambiguous: document defines multiple profiles"
    )


def build_base_context(
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
    steps: Mapping[str, Any] | None = None,
    imported_locals: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build base namespace mapping (without computed root locals/bindings)."""

    context: dict[str, Any] = {
        "params": dict(params),
        "locals": {},
        "profile": dict(selected_profile or {}),
        "run": dict(run or {}),
        "steps": dict(steps or {}),
        "bindings": {},
    }
    if imported_locals:
        for alias, values in imported_locals.items():
            context[alias] = {"locals": dict(values)}
    return context


def evaluate_imported_document_locals(
    imported_doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate imported document locals, including nested imports."""

    imported_ctx = build_imported_locals_context(
        imported_doc,
        params=params,
        selected_profile=selected_profile,
        run=run,
    )
    return evaluate_root_locals(
        imported_doc,
        params=params,
        selected_profile=selected_profile,
        run=run,
        imported_locals=imported_ctx,
    )


def build_imported_locals_context(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Recursively evaluate imported docs locals and return alias -> locals mapping."""

    imported: dict[str, dict[str, Any]] = {}
    for alias, imported_doc in doc.imported_documents.items():
        imported[alias] = evaluate_imported_document_locals(
            imported_doc,
            params=params,
            selected_profile=selected_profile,
            run=run,
        )
    return imported


def evaluate_root_locals(
    doc: V2Document,
    *,
    params: Mapping[str, Any],
    selected_profile: Mapping[str, Any] | None,
    run: Mapping[str, Any] | None = None,
    imported_locals: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate root locals top-to-bottom.

    Runtime constraints:
    - allowed in locals expressions: params/profile/earlier locals/imported ns.locals/run
    - forbidden by construction: steps/loop/error (missing from local eval context)
    """

    local_context = build_base_context(
        params=params,
        selected_profile=selected_profile,
        run=run,
        steps=None,
        imported_locals=imported_locals,
    )

    evaluated: dict[str, Any] = {}
    local_context["locals"] = evaluated

    for name, raw_value in doc.locals.items():
        try:
            evaluated[name] = render_scalar_or_ref(raw_value, local_context)
        except Exception as exc:  # noqa: BLE001
            raise V2ExecutionError(
                f"failed to evaluate local '{name}' in document {doc.source_path}: {exc}"
            ) from exc

    return evaluated


def merge_with_bindings(
    context: Mapping[str, Any],
    with_values: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge `with` bindings as short-name candidates without altering namespaces."""

    merged = dict(context)
    merged["bindings"] = dict(with_values or {})
    for key, value in (with_values or {}).items():
        if key in ROOT_NAMESPACE_KEYS:
            continue
        merged[key] = value
    return merged


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
    """Build typed runtime context for renderer/expression engine consumers."""

    profile = resolve_selected_profile(
        doc,
        selected_profile_name=selected_profile_name,
        selected_profile=selected_profile,
    )
    imported = build_imported_locals_context(
        doc,
        params=params,
        selected_profile=profile,
        run=run,
    )
    root_locals = evaluate_root_locals(
        doc,
        params=params,
        selected_profile=profile,
        run=run,
        imported_locals=imported,
    )

    runtime_ctx = RunContext(
        params=dict(params),
        locals=root_locals,
        profile=profile,
        run=dict(run or {}),
        steps=dict(steps or {}),
        loop=dict(loop) if loop is not None else None,
        error=dict(error) if error is not None else None,
        imported={alias: {"locals": dict(values)} for alias, values in imported.items()} if imported else None,
        bindings=dict(with_values or {}),
    )

    mapping = runtime_ctx.as_mapping()
    merged = merge_with_bindings(mapping, with_values)
    runtime_ctx.bindings = dict(merged.get("bindings", {}))
    return runtime_ctx


def context_to_mapping(run_context: RunContext) -> dict[str, Any]:
    """Return runtime context as a plain mapping."""

    return run_context.as_mapping()


def _profile_to_mapping(profile_def: Any) -> dict[str, Any]:
    if profile_def is None:
        return {}
    if isinstance(profile_def, Mapping):
        return dict(profile_def)
    # ProfileDef dataclass
    mapping: dict[str, Any] = {}
    for key in ("workdir", "env", "runtimes"):
        value = getattr(profile_def, key, None)
        if value is None:
            continue
        mapping[key] = dict(value) if isinstance(value, Mapping) else value
    return mapping
