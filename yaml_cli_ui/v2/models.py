"""Core typed structures for YAML CLI UI v2 document and runtime scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ImportDef:
    """Named import of another YAML document.

    alias: alias used in callable namespace.
    path: filesystem path to imported YAML document.
    """

    alias: str
    path: str


@dataclass(slots=True)
class ProfileDef:
    """Execution profile defaults.

    env: profile-level environment overrides.
    workdir: optional default working directory.
    runtimes: runtime alias map (e.g. python -> executable path).
    """

    env: dict[str, str] = field(default_factory=dict)
    workdir: str | None = None
    runtimes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParamDef:
    """Parameter definition exposed to UI layer in v2."""

    type: str
    title: str | None = None
    required: bool = False
    default: Any = None


@dataclass(slots=True)
class RunSpec:
    """Command run configuration for launching a process."""

    program: str
    argv: list[Any] = field(default_factory=list)
    workdir: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class OnErrorSpec:
    """Recovery behavior for failed command/pipeline execution."""

    use: str | None = None
    with_args: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommandDef:
    """Callable command definition in v2 document."""

    run: RunSpec
    title: str | None = None
    info: str | None = None
    when: Any = True
    continue_on_error: bool = False
    on_error: OnErrorSpec | None = None


@dataclass(slots=True)
class ForeachSpec:
    """Foreach iteration block for pipeline steps."""

    source: Any
    alias: str
    steps: list[StepSpec] = field(default_factory=list)


@dataclass(slots=True)
class StepSpec:
    """Pipeline step: callable invocation or foreach block."""

    step: str | None = None
    use: str | None = None
    with_args: dict[str, Any] = field(default_factory=dict)
    when: Any = True
    continue_on_error: bool = False
    foreach: ForeachSpec | None = None


@dataclass(slots=True)
class PipelineDef:
    """Callable pipeline definition composed of ordered steps."""

    steps: list[StepSpec] = field(default_factory=list)
    title: str | None = None
    info: str | None = None
    when: Any = True
    continue_on_error: bool = False
    on_error: OnErrorSpec | None = None


@dataclass(slots=True)
class LauncherDef:
    """Top-level launcher entry used by UI."""

    title: str
    use: str
    info: str | None = None
    with_args: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ErrorContext:
    """Structured context exposed to on_error handlers and logs."""

    step: str
    type: str
    message: str
    exit_code: int | None = None


@dataclass(slots=True)
class StepResult:
    """Minimal runtime step result tracked by executor scaffold."""

    status: str
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None


@dataclass(slots=True)
class RunContext:
    """Runtime context for expression/render/execution stages."""

    params: dict[str, Any] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, StepResult] = field(default_factory=dict)


@dataclass(slots=True)
class V2Document:
    """Parsed v2 YAML document.

    raw: original YAML dictionary.
    version: document format version.
    imports/profiles/params/commands/pipelines/launchers: typed top-level sections.
    """

    raw: dict[str, Any]
    version: int
    imports: dict[str, ImportDef] = field(default_factory=dict)
    profiles: dict[str, ProfileDef] = field(default_factory=dict)
    params: dict[str, ParamDef] = field(default_factory=dict)
    commands: dict[str, CommandDef] = field(default_factory=dict)
    pipelines: dict[str, PipelineDef] = field(default_factory=dict)
    launchers: dict[str, LauncherDef] = field(default_factory=dict)


__all__ = [
    "CommandDef",
    "ErrorContext",
    "ForeachSpec",
    "ImportDef",
    "LauncherDef",
    "OnErrorSpec",
    "ParamDef",
    "PipelineDef",
    "ProfileDef",
    "RunContext",
    "RunSpec",
    "StepResult",
    "StepSpec",
    "V2Document",
]
