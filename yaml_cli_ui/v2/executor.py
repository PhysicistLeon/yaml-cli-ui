"""Single-command execution runtime for YAML CLI UI v2.

EBNF summary for this step:

- CommandExecution :=
    if when == false -> skipped result
    else resolve program -> serialize argv -> resolve workdir -> build env
         -> execute subprocess -> map to StepResult
- StdStreamMode := "capture" | "inherit" | "file:" path
- ResultStatus := success | failed | skipped
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from .argv import serialize_argv
from .errors import V2ExecutionError
from .models import CommandDef, ErrorContext, RunSpec, StepResult, StepStatus
from .results import PipelineResult
from .renderer import render_scalar_or_ref


def resolve_program(program: str, context: Mapping[str, Any]) -> str:
    """Resolve program with optional profile runtime override."""

    profile = _profile_mapping(context)
    runtimes = profile.get("runtimes")
    if isinstance(runtimes, Mapping):
        override = runtimes.get(program)
        if isinstance(override, str) and override:
            return override
    return program


def resolve_workdir(run_spec: RunSpec, context: Mapping[str, Any]) -> str | None:
    """Resolve subprocess working directory from run or profile defaults."""

    source: Any | None = run_spec.workdir
    if source is None:
        profile = _profile_mapping(context)
        source = profile.get("workdir")
    if source is None:
        return None

    rendered = render_scalar_or_ref(source, context)
    if not isinstance(rendered, str):
        raise V2ExecutionError("workdir must render to string")
    return rendered


def build_process_env(run_spec: RunSpec, context: Mapping[str, Any]) -> dict[str, str]:
    """Build deterministic process environment.

    Merge order:
      1) os.environ
      2) profile.env
      3) run_spec.env (with renderer evaluation)
    """

    merged = dict(os.environ)
    profile = _profile_mapping(context)

    profile_env = profile.get("env")
    if profile_env is not None:
        if not isinstance(profile_env, Mapping):
            raise V2ExecutionError("profile.env must be a mapping")
        for key, value in profile_env.items():
            merged[str(key)] = _coerce_env_value(value, label=f"profile.env['{key}']")

    if not isinstance(run_spec.env, Mapping):
        raise V2ExecutionError("run.env must be a mapping")
    for key, raw_value in run_spec.env.items():
        rendered = render_scalar_or_ref(raw_value, context)
        merged[str(key)] = _coerce_env_value(rendered, label=f"run.env['{key}']")

    return merged


def execute_command_def(
    command: CommandDef,
    *,
    context: Mapping[str, Any],
    step_name: str | None = None,
) -> StepResult:
    """Execute a single command callable definition."""

    name = step_name or command.title or command.run.program
    if command.when is not None:
        when_value = render_scalar_or_ref(command.when, context)
        if not bool(when_value):
            now = _now_utc()
            return StepResult(
                name=name,
                status=StepStatus.SKIPPED,
                exit_code=None,
                stdout=None,
                stderr=None,
                duration_ms=0,
                started_at=now,
                finished_at=now,
            )

    return execute_run_spec(command.run, context=context, step_name=name)


def execute_run_spec(run_spec: RunSpec, *, context: Mapping[str, Any], step_name: str) -> StepResult:
    """Execute a resolved RunSpec using subprocess without shell splitting."""

    program = resolve_program(run_spec.program, context)
    argv = serialize_argv(run_spec.argv, context)
    workdir = resolve_workdir(run_spec, context)
    env = build_process_env(run_spec, context)

    stdout_target, stdout_mode, stdout_file = _resolve_stream_target(run_spec.stdout, context, "stdout")
    stderr_target, stderr_mode, stderr_file = _resolve_stream_target(run_spec.stderr, context, "stderr")

    started_at = _now_utc()
    try:
        completed = subprocess.run(
            [program, *argv],
            cwd=workdir,
            env=env,
            stdout=stdout_target,
            stderr=stderr_target,
            text=True,
            shell=False,
            timeout=(run_spec.timeout_ms / 1000.0) if run_spec.timeout_ms is not None else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        finished_at = _now_utc()
        _close_if_open(stdout_file)
        _close_if_open(stderr_file)
        return StepResult(
            name=step_name,
            status=StepStatus.FAILED,
            exit_code=None,
            stdout=exc.stdout if stdout_mode == "capture" else None,
            stderr=exc.stderr if stderr_mode == "capture" else None,
            duration_ms=_duration_ms(started_at, finished_at),
            started_at=started_at,
            finished_at=finished_at,
            error=ErrorContext(
                type="timeout",
                message=f"command timed out after {run_spec.timeout_ms} ms",
                step=step_name,
            ),
            meta={"program": program, "argv": argv, "workdir": workdir},
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        _close_if_open(stdout_file)
        _close_if_open(stderr_file)
        raise V2ExecutionError(f"failed to start program '{program}': {exc}") from exc
    finally:
        _close_if_open(stdout_file)
        _close_if_open(stderr_file)

    finished_at = _now_utc()
    exit_code = completed.returncode
    status = StepStatus.SUCCESS if exit_code == 0 else StepStatus.FAILED

    return StepResult(
        name=step_name,
        status=status,
        exit_code=exit_code,
        stdout=completed.stdout if stdout_mode == "capture" else None,
        stderr=completed.stderr if stderr_mode == "capture" else None,
        duration_ms=_duration_ms(started_at, finished_at),
        started_at=started_at,
        finished_at=finished_at,
        meta={"program": program, "argv": argv, "workdir": workdir},
    )


def execute_launcher(doc: Any, launcher_name: str, context: Any) -> PipelineResult:
    """Execute launcher target in v2 runtime (placeholder)."""

    raise NotImplementedError("v2 launcher/pipeline executor is deferred")


def _resolve_stream_target(
    raw_mode: str | None,
    context: Mapping[str, Any],
    stream_name: str,
) -> tuple[int | TextIO, str, TextIO | None]:
    mode = raw_mode or "capture"
    if mode == "capture":
        return subprocess.PIPE, "capture", None
    if mode == "inherit":
        return None, "inherit", None
    if mode.startswith("file:"):
        path_template = mode.split(":", 1)[1]
        rendered = render_scalar_or_ref(path_template, context)
        if not isinstance(rendered, str) or not rendered:
            raise V2ExecutionError(f"{stream_name} file path must render to non-empty string")
        try:
            file_handle = Path(rendered).open("w", encoding="utf-8")
        except OSError as exc:
            raise V2ExecutionError(f"failed to open {stream_name} file '{rendered}': {exc}") from exc
        return file_handle, "file", file_handle
    raise V2ExecutionError(f"unsupported {stream_name} mode '{mode}'")


def _coerce_env_value(value: Any, *, label: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return str(value)
    raise V2ExecutionError(f"{label} must render to string/number/bool")


def _profile_mapping(context: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = context.get("profile")
    if profile is None:
        return {}
    if not isinstance(profile, Mapping):
        raise V2ExecutionError("context.profile must be a mapping")
    return profile


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _close_if_open(handle: TextIO | None) -> None:
    if handle is not None:
        handle.close()


__all__ = [
    "resolve_program",
    "resolve_workdir",
    "build_process_env",
    "execute_command_def",
    "execute_run_spec",
    "execute_launcher",
]
