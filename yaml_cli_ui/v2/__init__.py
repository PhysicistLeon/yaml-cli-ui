"""Public API surface for YAML CLI UI v2 scaffold."""

from .expr import evaluate_expression, resolve_name
from .context import (
    build_base_context,
    build_imported_locals_context,
    build_runtime_context,
    context_to_mapping,
    evaluate_imported_document_locals,
    evaluate_root_locals,
    merge_with_bindings,
    resolve_selected_profile,
)
from .loader import load_v2_document, load_yaml_file, resolve_imports
from .renderer import render_scalar_or_ref, render_string, render_value
from .models import (
    PUBLIC_API_MODELS,
    CommandDef,
    ErrorContext,
    ForeachSpec,
    LauncherDef,
    ParamDef,
    ParamType,
    PipelineDef,
    ProfileDef,
    RunContext,
    RunSpec,
    SecretSource,
    StepResult,
    StepSpec,
    StepStatus,
    V2Document,
)
from .validator import validate_v2_document

# Keep direct references so linters treat model re-exports as used symbols.
_EXPORTED_MODEL_SYMBOLS = (
    CommandDef,
    ErrorContext,
    ForeachSpec,
    LauncherDef,
    ParamDef,
    ParamType,
    PipelineDef,
    ProfileDef,
    RunContext,
    RunSpec,
    SecretSource,
    StepResult,
    StepSpec,
    StepStatus,
    V2Document,
)

__all__ = [
    *PUBLIC_API_MODELS,
    "load_yaml_file",
    "resolve_imports",
    "load_v2_document",
    "validate_v2_document",
    "evaluate_expression",
    "resolve_name",
    "render_value",
    "render_string",
    "render_scalar_or_ref",
    "resolve_selected_profile",
    "build_base_context",
    "evaluate_root_locals",
    "merge_with_bindings",
    "build_runtime_context",
    "build_imported_locals_context",
    "evaluate_imported_document_locals",
    "context_to_mapping",
]
