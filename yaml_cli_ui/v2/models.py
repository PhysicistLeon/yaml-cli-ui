"""Core typed data models for YAML CLI UI v2-lite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class ParamType(str, Enum):
    """Supported parameter types in v2-lite."""

    STRING = "string"
    TEXT = "text"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    CHOICE = "choice"
    MULTICHOICE = "multichoice"
    FILEPATH = "filepath"
    DIRPATH = "dirpath"
    SECRET = "secret"
    KV_LIST = "kv_list"
    STRUCT_LIST = "struct_list"


class SecretSource(str, Enum):
    """Secret source backends supported by v2-lite."""

    ENV = "env"
    VAULT = "vault"


class StepKind(str, Enum):
    """Discriminator for expanded pipeline step shape."""

    USE = "use"
    FOREACH = "foreach"


class ArgvItemKind(str, Enum):
    """Reserved argv item categories for future argv DSL typing."""

    LITERAL = "literal"
    EXPR = "expr"


class StepStatus(str, Enum):
    """Execution status of a step."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


@dataclass(slots=True)
class ImportDef:
    """Named import declaration."""

    alias: str
    path: str
    resolved_path: Path | None = None


@dataclass(slots=True)
class ProfileDef:
    """Execution profile defaults."""

    workdir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    runtimes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParamDef:
    """UI-visible parameter schema for v2-lite."""

    type: ParamType
    title: str | None = None
    required: bool = False
    default: Any | None = None
    options: list[Any] | None = None
    widget: str | None = None
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    must_exist: bool | None = None
    source: SecretSource | None = None
    env: str | None = None
    key: str | None = None
    item_schema: dict[str, "ParamDef"] | None = None


@dataclass(slots=True)
class RunSpec:
    """Process execution spec for command callables."""

    program: str
    argv: list[Any] = field(default_factory=list)
    workdir: Any | None = None
    env: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None
    stdout: str | None = None
    stderr: str | None = None

    def __post_init__(self) -> None:
        if not self.program or not isinstance(self.program, str):
            raise ValueError("RunSpec.program must be a non-empty string")


@dataclass(slots=True)
class OnErrorSpec:
    """Fallback steps to run when owner callable fails."""

    steps: list["StepSpec | str"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("OnErrorSpec.steps must not be empty")


@dataclass(slots=True)
class ForeachSpec:
    """Foreach iterator block in a pipeline step."""

    in_expr: Any
    as_name: str
    steps: list["StepSpec | str"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.as_name:
            raise ValueError("ForeachSpec.as_name must be a non-empty string")
        if not self.steps:
            raise ValueError("ForeachSpec.steps must not be empty")


@dataclass(slots=True)
class StepSpec:
    """Expanded pipeline step (callable use or foreach block)."""

    step: str | None = None
    when: Any | None = None
    continue_on_error: bool = False
    use: str | None = None
    with_values: dict[str, Any] = field(default_factory=dict)
    foreach: ForeachSpec | None = None

    def __post_init__(self) -> None:
        has_use = self.use is not None
        has_foreach = self.foreach is not None

        if has_use and isinstance(self.use, str) and not self.use.strip():
            raise ValueError("StepSpec.use must be a non-empty string when provided")

        if has_use == has_foreach:
            raise ValueError("StepSpec must define exactly one of 'use' or 'foreach'")

    @property
    def kind(self) -> StepKind | None:
        """Infer step kind from populated fields."""

        has_use = self.use is not None
        has_foreach = self.foreach is not None
        if has_use and not has_foreach:
            return StepKind.USE
        if has_foreach and not has_use:
            return StepKind.FOREACH
        return None

    @property
    def is_use_step(self) -> bool:
        return self.kind == StepKind.USE

    @property
    def is_foreach_step(self) -> bool:
        return self.kind == StepKind.FOREACH


@dataclass(slots=True)
class CommandDef:
    """Command callable definition."""

    run: RunSpec
    title: str | None = None
    info: str | None = None
    when: Any | None = None
    continue_on_error: bool = False
    on_error: OnErrorSpec | None = None

    def __post_init__(self) -> None:
        if self.run is None:
            raise ValueError("CommandDef.run is required")


@dataclass(slots=True)
class PipelineDef:
    """Pipeline callable definition."""

    steps: list[StepSpec | str] = field(default_factory=list)
    title: str | None = None
    info: str | None = None
    when: Any | None = None
    continue_on_error: bool = False
    on_error: OnErrorSpec | None = None

    def __post_init__(self) -> None:
        if self.steps is None:
            raise ValueError("PipelineDef.steps must not be None")


@dataclass(slots=True)
class LauncherDef:
    """Launcher definition used by UI as entry point."""

    title: str
    use: str
    info: str | None = None
    with_values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("LauncherDef.title must be a non-empty string")
        if not self.use:
            raise ValueError("LauncherDef.use must be a non-empty string")


@dataclass(slots=True)
class ErrorContext:
    """Normalized error data for step/callable failures."""

    type: str
    message: str
    step: str | None = None
    exit_code: int | None = None


@dataclass(slots=True)
class StepResult:
    """Execution result for a single command/pipeline step."""

    name: str
    status: StepStatus
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorContext | None = None
    children: dict[str, "StepResult"] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunContext:
    """Typed runtime context container shared by v2 stages."""

    params: dict[str, Any] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, Any] = field(default_factory=dict)
    loop: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    imported: dict[str, dict[str, Any]] | None = None
    bindings: dict[str, Any] = field(default_factory=dict)

    def as_mapping(self) -> dict[str, Any]:
        """Return renderer/evaluator-ready mapping representation."""

        payload: dict[str, Any] = {
            "params": dict(self.params),
            "locals": dict(self.locals),
            "profile": dict(self.profile),
            "run": dict(self.run),
            "steps": dict(self.steps),
            "bindings": dict(self.bindings),
        }
        if self.loop is not None:
            payload["loop"] = dict(self.loop)
        if self.error is not None:
            payload["error"] = dict(self.error)
        for alias, values in (self.imported or {}).items():
            payload[alias] = {"locals": dict(values)}
        return payload


@dataclass(slots=True)
class V2Document:
    """Top-level v2-lite document model."""

    version: int = 2
    imports: dict[str, ImportDef] = field(default_factory=dict)
    profiles: dict[str, ProfileDef] = field(default_factory=dict)
    params: dict[str, ParamDef] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    commands: dict[str, CommandDef] = field(default_factory=dict)
    pipelines: dict[str, PipelineDef] = field(default_factory=dict)
    launchers: dict[str, LauncherDef] = field(default_factory=dict)
    imported_documents: dict[str, "V2Document"] = field(default_factory=dict)
    source_path: Path | None = None
    base_dir: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version is None:
            self.version = 2

    def callables(self) -> dict[str, CommandDef | PipelineDef]:
        """Return merged callable namespace: commands + pipelines."""

        conflicts = set(self.commands).intersection(self.pipelines)
        if conflicts:
            conflict_list = ", ".join(sorted(conflicts))
            raise ValueError(
                "V2Document callable namespace conflict between commands and pipelines: "
                f"{conflict_list}"
            )
        return {**self.commands, **self.pipelines}

    def has_profile(self, name: str) -> bool:
        """Check whether profile exists in the document."""

        return name in self.profiles


PUBLIC_API_MODELS = (
    "CommandDef",
    "ErrorContext",
    "ForeachSpec",
    "LauncherDef",
    "ParamDef",
    "ParamType",
    "PipelineDef",
    "ProfileDef",
    "RunContext",
    "RunSpec",
    "SecretSource",
    "StepResult",
    "StepSpec",
    "StepStatus",
    "V2Document",
)

__all__ = [
    "ArgvItemKind",
    "ImportDef",
    "OnErrorSpec",
    "StepKind",
    "CommandDef",
    "ErrorContext",
    "ForeachSpec",
    "LauncherDef",
    "ParamDef",
    "ParamType",
    "PipelineDef",
    "ProfileDef",
    "RunContext",
    "RunSpec",
    "SecretSource",
    "StepResult",
    "StepSpec",
    "StepStatus",
    "V2Document",
]
