"""Single-command executor for YAML CLI UI v2.

Minimal EBNF for this step:

CommandExecution :=
  if when == false -> skipped result
  else
    resolve program
    serialize argv
    resolve workdir
    build env
    execute subprocess
    collect stdout/stderr/exit_code/timing
    map to StepResult

StdStreamMode :=
    "capture"
  | "inherit"
  | "file:" path

ResultStatus :=
    success
  | failed
  | skipped
"""

from __future__ import annotations

import os
import subprocess
from contextlib import ExitStack
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Mapping

from .argv import serialize_argv
from .errors import V2ExecutionError
from .expr import evaluate_expression
from .models import CommandDef, ErrorContext, RunSpec, StepResult, StepStatus
from .renderer import render_scalar_or_ref, render_string


def resolve_program(program: str, context: Mapping[str, Any]) -> str:
    """Resolve runtime program with optional profile.runtimes override."""

    profile = context.get("profile")
    runtimes = profile.get("runtimes") if isinstance(profile, Mapping) else None
    if isinstance(runtimes, Mapping) and program in runtimes:
        resolved = runtimes[program]
        if not isinstance(resolved, str) or not resolved:
            raise V2ExecutionError(
                f"profile.runtimes['{program}'] must be a non-empty string"
            )
        return resolved
    return program


def resolve_workdir(run_spec: RunSpec, context: Mapping[str, Any]) -> str | None:
    """Resolve effective subprocess cwd from run_spec or profile defaults."""

    source = run_spec.workdir
    if source is None:
        profile = context.get("profile")
        if isinstance(profile, Mapping):
            source = profile.get("workdir")

    if source is None:
        return None

    rendered = render_scalar_or_ref(source, context)
    if not isinstance(rendered, str):
        raise V2ExecutionError("workdir must render to a string")
    return rendered


def build_process_env(run_spec: RunSpec, context: Mapping[str, Any]) -> dict[str, str]:
    """Build effective process env with deterministic merge order."""

    merged: dict[str, str] = dict(os.environ)

    profile = context.get("profile")
    if isinstance(profile, Mapping):
        profile_env = profile.get("env")
        if profile_env is not None:
            if not isinstance(profile_env, Mapping):
                raise V2ExecutionError("profile.env must be a mapping")
            _merge_env_map(merged, profile_env, context, source_label="profile.env", render_values=False)

    _merge_env_map(merged, run_spec.env, context, source_label="run.env", render_values=True)
    return merged


def execute_command_def(
    command: CommandDef,
    *,
    context: Mapping[str, Any],
    step_name: str | None = None,
) -> StepResult:
    """Execute a single command definition and return normalized step result."""

    name = step_name or command.title or "command"
    if command.when is not None and not _evaluate_when(command.when, context):
        timestamp = _utcnow()
        return StepResult(
            name=name,
            status=StepStatus.SKIPPED,
            exit_code=None,
            stdout=None,
            stderr=None,
            duration_ms=0,
            started_at=timestamp,
            finished_at=timestamp,
            meta={"reason": "when=false"},
        )

    return execute_run_spec(command.run, context=context, step_name=name)


def execute_run_spec(
    run_spec: RunSpec,
    *,
    context: Mapping[str, Any],
    step_name: str,
) -> StepResult:
    """Execute run spec via subprocess without shell concatenation."""

    program = resolve_program(run_spec.program, context)
    argv = serialize_argv(run_spec.argv, context)
    workdir = resolve_workdir(run_spec, context)
    env = build_process_env(run_spec, context)

    stdout_mode, stdout_target = _parse_stream_mode(run_spec.stdout, context, stream_name="stdout")
    stderr_mode, stderr_target = _parse_stream_mode(run_spec.stderr, context, stream_name="stderr")

    started_at = _utcnow()
    start_perf = perf_counter()

    with ExitStack() as stack:
        stdout_handle = _open_stream_target(stack, stdout_mode, stdout_target, "stdout")
        stderr_handle = _open_stream_target(stack, stderr_mode, stderr_target, "stderr")

        try:
            completed = subprocess.run(
                [program, *argv],
                shell=False,
                cwd=workdir,
                env=env,
                text=True,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=(run_spec.timeout_ms / 1000.0) if run_spec.timeout_ms is not None else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            finished_at = _utcnow()
            duration_ms = _duration_ms(start_perf)
            return StepResult(
                name=step_name,
                status=StepStatus.FAILED,
                exit_code=None,
                stdout=_timeout_partial_output(exc.stdout, stdout_mode),
                stderr=_timeout_partial_output(exc.stderr, stderr_mode),
                duration_ms=duration_ms,
                started_at=started_at,
                finished_at=finished_at,
                error=ErrorContext(
                    type="timeout",
                    message=f"command timed out after {run_spec.timeout_ms} ms",
                    step=step_name,
                    exit_code=None,
                ),
                meta={"program": program, "argv": argv, "workdir": workdir},
            )
        except FileNotFoundError as exc:
            raise V2ExecutionError(f"failed to start program '{program}': {exc}") from exc
        except OSError as exc:
            raise V2ExecutionError(f"OS error while starting program '{program}': {exc}") from exc

    finished_at = _utcnow()
    duration_ms = _duration_ms(start_perf)
    status = StepStatus.SUCCESS if completed.returncode == 0 else StepStatus.FAILED

    return StepResult(
        name=step_name,
        status=status,
        exit_code=completed.returncode,
        stdout=completed.stdout if stdout_mode == "capture" else None,
        stderr=completed.stderr if stderr_mode == "capture" else None,
        duration_ms=duration_ms,
        started_at=started_at,
        finished_at=finished_at,
        error=None,
        meta={"program": program, "argv": argv, "workdir": workdir},
    )



def _evaluate_when(when: Any, context: Mapping[str, Any]) -> bool:
    if isinstance(when, str):
        stripped = when.strip()
        if stripped.startswith("${") and stripped.endswith("}"):
            return bool(evaluate_expression(stripped, context))
    return bool(render_scalar_or_ref(when, context))

def _merge_env_map(
    merged: dict[str, str],
    source: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    source_label: str,
    render_values: bool,
) -> None:
    if not isinstance(source, Mapping):
        raise V2ExecutionError(f"{source_label} must be a mapping")
    for key, raw_value in source.items():
        if not isinstance(key, str) or not key:
            raise V2ExecutionError(f"{source_label} keys must be non-empty strings")
        value = render_scalar_or_ref(raw_value, context) if render_values else raw_value
        merged[key] = _coerce_env_value(value, f"{source_label}.{key}")


def _coerce_env_value(value: Any, label: str) -> str:
    if isinstance(value, (str, bool, int, float)):
        return str(value)
    raise V2ExecutionError(
        f"{label} must render to scalar string/number/bool, got {type(value).__name__}"
    )


def _parse_stream_mode(
    raw_mode: str | None,
    context: Mapping[str, Any],
    *,
    stream_name: str,
) -> tuple[str, str | None]:
    mode = raw_mode or "capture"
    if mode in ("capture", "inherit"):
        return mode, None
    if mode.startswith("file:"):
        rendered = render_string(mode[5:], context)
        if not isinstance(rendered, str) or not rendered:
            raise V2ExecutionError(f"{stream_name} file path must render to non-empty string")
        return "file", rendered
    raise V2ExecutionError(
        f"unsupported {stream_name} mode '{mode}', expected capture|inherit|file:<path>"
    )


def _open_stream_target(
    stack: ExitStack,
    mode: str,
    target: str | None,
    stream_name: str,
):
    if mode == "capture":
        return subprocess.PIPE
    if mode == "inherit":
        return None
    if mode == "file":
        assert target is not None
        try:
            return stack.enter_context(open(target, "w", encoding="utf-8"))
        except OSError as exc:
            raise V2ExecutionError(
                f"failed to open {stream_name} file target '{target}': {exc}"
            ) from exc
    raise V2ExecutionError(f"internal unsupported stream mode '{mode}'")


def _timeout_partial_output(raw: Any, mode: str) -> str | None:
    if mode != "capture" or raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode(errors="replace")
    return str(raw)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start_perf: float) -> int:
    return max(0, int((perf_counter() - start_perf) * 1000))


EXECUTOR_PUBLIC_API = (
    "resolve_program",
    "resolve_workdir",
    "build_process_env",
    "execute_command_def",
    "execute_run_spec",
)

__all__ = list(EXECUTOR_PUBLIC_API)
