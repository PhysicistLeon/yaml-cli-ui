"""Execution engine for YAML CLI UI v2 commands and pipelines.

Minimal EBNF for this step:

PipelineExecution :=
  Step*

Step :=
  ShortCallableRef
| ExpandedUseStep
| ForeachStep

ShortCallableRef :=
  callable_name

ExpandedUseStep :=
  ["step": string]
  ["when": value]
  ["continue_on_error": bool]
  "use": callable_name
  ["with": map]

ForeachStep :=
  ["step": string]
  ["when": value]
  ["continue_on_error": bool]
  "foreach":
    "in": value
    "as": string
    "steps": Step*

OnError :=
  "steps": Step*
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
from .models import (
    CommandDef,
    ErrorContext,
    OnErrorSpec,
    PipelineDef,
    RunSpec,
    StepResult,
    StepSpec,
    StepStatus,
    V2Document,
)
from .renderer import render_scalar_or_ref, render_value


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


def resolve_callable(doc: V2Document, callable_name: str) -> CommandDef | PipelineDef:
    """Resolve local or imported callable by name."""

    if "." in callable_name:
        alias, nested_name = callable_name.split(".", 1)
        if not alias or not nested_name:
            raise V2ExecutionError(f"invalid callable name '{callable_name}'")
        imported_doc = doc.imported_documents.get(alias)
        if imported_doc is None:
            raise V2ExecutionError(f"unknown import alias '{alias}' in callable '{callable_name}'")
        return resolve_callable(imported_doc, nested_name)

    callable_obj = doc.callables().get(callable_name)
    if callable_obj is None:
        raise V2ExecutionError(f"callable '{callable_name}' not found")
    return callable_obj


def execute_command_def(
    command: CommandDef,
    *,
    context: Mapping[str, Any],
    step_name: str | None = None,
    doc: V2Document | None = None,
) -> StepResult:
    """Execute command and apply command-level on_error semantics."""

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

    result = execute_run_spec(command.run, context=context, step_name=name)
    if result.status != StepStatus.FAILED or command.on_error is None:
        return result

    error_context = make_error_context(result, owner_name=name)
    recovery = execute_on_error(
        command.on_error,
        doc=doc or _context_doc(context),
        context=context,
        error_context=_error_context_to_mapping(error_context) or {},
        owner_name=name,
    )
    if recovery.status in (StepStatus.SUCCESS, StepStatus.SKIPPED, StepStatus.RECOVERED):
        result.status = StepStatus.RECOVERED
        result.meta["on_error"] = recovery
        return result

    result.meta["recovery_error"] = _error_context_to_mapping(recovery.error)
    result.error = ErrorContext(
        type="command_recovery_failed",
        message=f"command failed and on_error recovery failed for '{name}'",
        step=name,
        exit_code=result.exit_code,
    )
    result.meta["on_error"] = recovery
    return result


def execute_pipeline_def(
    pipeline: PipelineDef,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    step_name: str | None = None,
) -> StepResult:
    """Execute pipeline sequentially and aggregate step results."""

    name = step_name or pipeline.title or "pipeline"
    started_at = _utcnow()
    start_perf = perf_counter()

    if pipeline.when is not None and not _evaluate_when(pipeline.when, context):
        return StepResult(
            name=name,
            status=StepStatus.SKIPPED,
            exit_code=None,
            stdout=None,
            stderr=None,
            duration_ms=0,
            started_at=started_at,
            finished_at=started_at,
            children={},
            meta={"reason": "when=false"},
        )

    children: dict[str, StepResult] = {}
    pipeline_steps = _copy_steps_mapping(context)
    generated_index = 0
    hard_failure: StepResult | None = None
    had_soft_failures = False

    for raw_step in pipeline.steps:
        step_context = make_child_steps_mapping(context, pipeline_steps)
        step_result = execute_step(
            raw_step,
            doc=doc,
            context=step_context,
            generated_name_index=generated_index,
        )
        generated_index += 1

        if step_result.name in children:
            step_result.name = _make_unique_step_name(step_result.name, children)

        children[step_result.name] = step_result
        pipeline_steps[step_result.name] = _step_result_to_context(step_result)

        if step_result.status != StepStatus.FAILED:
            continue

        effective_continue = _step_continue_on_error(raw_step, doc) or pipeline.continue_on_error
        if effective_continue:
            had_soft_failures = True
            continue

        hard_failure = step_result
        break

    duration = _duration_ms(start_perf)
    finished_at = _utcnow()

    if hard_failure is not None:
        base_result = StepResult(
            name=name,
            status=StepStatus.FAILED,
            duration_ms=duration,
            started_at=started_at,
            finished_at=finished_at,
            children=children,
            error=make_error_context(hard_failure, owner_name=name),
            meta={},
        )
        if pipeline.on_error is not None:
            recovery = execute_on_error(
                pipeline.on_error,
                doc=doc,
                context=make_child_steps_mapping(context, pipeline_steps),
                error_context=_error_context_to_mapping(base_result.error),
                owner_name=name,
            )
            base_result.meta["on_error"] = recovery
            if recovery.status in (StepStatus.SUCCESS, StepStatus.SKIPPED, StepStatus.RECOVERED):
                base_result.status = StepStatus.RECOVERED
            else:
                base_result.meta["recovery_error"] = _error_context_to_mapping(recovery.error)
                base_result.error = ErrorContext(
                    type="pipeline_recovery_failed",
                    message=f"pipeline failed and on_error recovery failed for '{name}'",
                    step=hard_failure.name,
                    exit_code=hard_failure.exit_code,
                )
        return base_result

    status = StepStatus.FAILED if had_soft_failures else StepStatus.SUCCESS
    return StepResult(
        name=name,
        status=status,
        duration_ms=duration,
        started_at=started_at,
        finished_at=finished_at,
        children=children,
        meta={},
    )


def execute_step(
    step: str | StepSpec,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    generated_name_index: int = 0,
) -> StepResult:
    """Execute one pipeline step entry."""

    normalized = normalize_step_spec(step)
    children = _copy_steps_mapping(context)

    if isinstance(normalized, str):
        callable_name = normalized
        step_name = _deduce_step_name(callable_name, generated_name_index, children)
        return execute_callable_name(callable_name, doc=doc, context=context, step_name=step_name)

    if normalized.when is not None and not _evaluate_when(normalized.when, context):
        timestamp = _utcnow()
        return StepResult(
            name=normalized.step or _generated_step_name(generated_name_index),
            status=StepStatus.SKIPPED,
            duration_ms=0,
            started_at=timestamp,
            finished_at=timestamp,
            meta={"reason": "when=false"},
        )

    if normalized.is_foreach_step:
        step_name = normalized.step or _generated_step_name(generated_name_index)
        foreach_result = execute_foreach_step(normalized, doc=doc, context=context)
        foreach_result.name = step_name
        return foreach_result

    if not normalized.use:
        raise V2ExecutionError("expanded step must define 'use'")

    step_name = normalized.step or _deduce_step_name(normalized.use, generated_name_index, children)
    step_context = _with_short_bindings(context, normalized.with_values)
    return execute_callable_name(normalized.use, doc=doc, context=step_context, step_name=step_name)


def execute_foreach_step(
    step: StepSpec,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
) -> StepResult:
    """Execute foreach block as per-iteration nested pipeline."""

    if step.foreach is None:
        raise V2ExecutionError("execute_foreach_step expects step.foreach")

    started_at = _utcnow()
    start_perf = perf_counter()

    items = render_value(step.foreach.in_expr, context)
    if not isinstance(items, list):
        raise V2ExecutionError("foreach.in must evaluate to a list")

    iteration_children: dict[str, StepResult] = {}
    success_count = 0
    failed_count = 0

    for index, item in enumerate(items):
        loop_ctx = {
            "index": index,
            "first": index == 0,
            "last": index == len(items) - 1,
        }
        iteration_context = dict(context)
        iteration_context[step.foreach.as_name] = item
        iteration_context["loop"] = loop_ctx
        iteration_result = execute_pipeline_def(
            PipelineDef(steps=list(step.foreach.steps)),
            doc=doc,
            context=iteration_context,
            step_name=f"iter_{index}",
        )
        iteration_children[f"iter_{index}"] = iteration_result

        if iteration_result.status == StepStatus.FAILED:
            failed_count += 1
        else:
            success_count += 1

    status = StepStatus.FAILED if failed_count else StepStatus.SUCCESS
    return StepResult(
        name=step.step or "foreach",
        status=status,
        duration_ms=_duration_ms(start_perf),
        started_at=started_at,
        finished_at=_utcnow(),
        children=iteration_children,
        meta={
            "iteration_count": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
        },
    )


def execute_on_error(
    on_error: OnErrorSpec,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    error_context: Mapping[str, Any],
    owner_name: str,
) -> StepResult:
    """Execute on_error fallback steps in error-aware context."""

    recovery_context = dict(context)
    recovery_context["error"] = dict(error_context)
    recovery = execute_pipeline_def(
        PipelineDef(steps=list(on_error.steps)),
        doc=doc,
        context=recovery_context,
        step_name=f"{owner_name}__on_error",
    )
    if recovery.status == StepStatus.SUCCESS:
        recovery.status = StepStatus.RECOVERED
    return recovery


def execute_callable_name(
    callable_name: str,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    step_name: str,
) -> StepResult:
    """Execute resolved callable (command or pipeline)."""

    callable_def = resolve_callable(doc, callable_name)
    if isinstance(callable_def, CommandDef):
        return execute_command_def(callable_def, context=context, step_name=step_name, doc=doc)
    return execute_pipeline_def(callable_def, doc=doc, context=context, step_name=step_name)


def normalize_step_spec(step: str | StepSpec) -> str | StepSpec:
    """Validate supported step shape in execution phase."""

    if isinstance(step, str):
        if not step.strip():
            raise V2ExecutionError("step callable name must be non-empty")
        return step
    if isinstance(step, StepSpec):
        return step
    raise V2ExecutionError(f"unsupported step type: {type(step).__name__}")


def make_error_context(result: StepResult, *, owner_name: str) -> ErrorContext:
    """Build error context from a failed result."""

    if result.error is not None:
        return ErrorContext(
            type=result.error.type,
            message=result.error.message,
            step=result.name,
            exit_code=result.error.exit_code,
        )
    return ErrorContext(
        type="execution_failed",
        message=f"step '{result.name}' failed in '{owner_name}'",
        step=result.name,
        exit_code=result.exit_code,
    )


def make_child_steps_mapping(
    context: Mapping[str, Any],
    steps_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Return context copy with updated $steps namespace."""

    child = dict(context)
    child["steps"] = dict(steps_mapping)
    return child


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
        rendered = render_scalar_or_ref(mode[5:], context)
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


def _with_short_bindings(context: Mapping[str, Any], with_values: Mapping[str, Any]) -> dict[str, Any]:
    rendered = {key: render_value(value, context) for key, value in with_values.items()}
    merged = dict(context)
    bindings = dict(context.get("bindings", {})) if isinstance(context.get("bindings"), Mapping) else {}
    bindings.update(rendered)
    merged["bindings"] = bindings
    return merged


def _step_continue_on_error(step: str | StepSpec, doc: V2Document) -> bool:
    if isinstance(step, StepSpec):
        if step.continue_on_error:
            return True
        if step.use:
            callable_def = resolve_callable(doc, step.use)
            if isinstance(callable_def, (CommandDef, PipelineDef)):
                return bool(callable_def.continue_on_error)
        return False

    callable_def = resolve_callable(doc, step)
    if isinstance(callable_def, (CommandDef, PipelineDef)):
        return bool(callable_def.continue_on_error)
    return False


def _context_doc(context: Mapping[str, Any]) -> V2Document:
    doc = context.get("_doc")
    if not isinstance(doc, V2Document):
        raise V2ExecutionError("internal context is missing '_doc' document reference")
    return doc


def _copy_steps_mapping(context: Mapping[str, Any]) -> dict[str, Any]:
    raw = context.get("steps", {})
    return dict(raw) if isinstance(raw, Mapping) else {}


def _deduce_step_name(callable_name: str, generated_name_index: int, children: Mapping[str, Any]) -> str:
    base = callable_name.rsplit(".", 1)[-1] if "." in callable_name else callable_name
    if not base:
        base = _generated_step_name(generated_name_index)
    return _make_unique_step_name(base, children)


def _generated_step_name(index: int) -> str:
    return f"step_{index + 1}"


def _make_unique_step_name(base: str, existing: Mapping[str, Any]) -> str:
    if base not in existing:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    return f"{base}_{suffix}"


def _step_result_to_context(result: StepResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "error": _error_context_to_mapping(result.error),
        "meta": dict(result.meta),
    }


def _error_context_to_mapping(error: ErrorContext | None) -> dict[str, Any] | None:
    if error is None:
        return None
    return {
        "type": error.type,
        "message": error.message,
        "step": error.step,
        "exit_code": error.exit_code,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start_perf: float) -> int:
    return max(0, int((perf_counter() - start_perf) * 1000))


EXECUTOR_PUBLIC_API = (
    "resolve_program",
    "resolve_workdir",
    "build_process_env",
    "resolve_callable",
    "execute_command_def",
    "execute_pipeline_def",
    "execute_step",
    "execute_foreach_step",
    "execute_on_error",
    "execute_run_spec",
)

__all__ = list(EXECUTOR_PUBLIC_API)
