"""Public API surface for YAML CLI UI v2 scaffold."""

from .argv import is_conditional_item, is_option_map, serialize_argv, serialize_argv_item
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
from .executor import (
    EXECUTOR_PUBLIC_API as _EXECUTOR_PUBLIC_API,
    build_process_env as _build_process_env,
    execute_command_def as _execute_command_def,
    execute_run_spec as _execute_run_spec,
    resolve_program as _resolve_program,
    resolve_workdir as _resolve_workdir,
)
from .expr import evaluate_expression, resolve_name
from .loader import load_v2_document, load_yaml_file, resolve_imports
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
from .renderer import render_scalar_or_ref, render_string, render_value
from .validator import validate_v2_document

resolve_program = _resolve_program
resolve_workdir = _resolve_workdir
build_process_env = _build_process_env
execute_command_def = _execute_command_def
execute_run_spec = _execute_run_spec

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
    "serialize_argv",
    "serialize_argv_item",
    "is_option_map",
    "is_conditional_item",
    *_EXECUTOR_PUBLIC_API,
    "resolve_selected_profile",
    "build_base_context",
    "evaluate_root_locals",
    "merge_with_bindings",
    "build_runtime_context",
    "build_imported_locals_context",
    "evaluate_imported_document_locals",
    "context_to_mapping",
]
