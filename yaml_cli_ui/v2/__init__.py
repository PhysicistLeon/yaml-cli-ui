"""Public API surface for YAML CLI UI v2 scaffold."""

from .expr import evaluate_expression, resolve_name
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
]
