"""Execution engine for YAML CLI UI v2.

Minimal EBNF for this step:
PipelineExecution := Step*
Step := ShortCallableRef | ExpandedUseStep | ForeachStep
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
from .renderer import render_scalar_or_ref, render_string


def resolve_program(program: str, context: Mapping[str, Any]) -> str:
    profile = context.get("profile")
    runtimes = profile.get("runtimes") if isinstance(profile, Mapping) else None
    if isinstance(runtimes, Mapping) and program in runtimes:
        resolved = runtimes[program]
        if not isinstance(resolved, str) or not resolved:
            raise V2ExecutionError(f"profile.runtimes['{program}'] must be a non-empty string")
        return resolved
    return program


def resolve_workdir(run_spec: RunSpec, context: Mapping[str, Any]) -> str | None:
    source = run_spec.workdir
    if source is None and isinstance(context.get("profile"), Mapping):
        source = context["profile"].get("workdir")
    if source is None:
        return None
    rendered = render_scalar_or_ref(source, context)
    if not isinstance(rendered, str):
        raise V2ExecutionError("workdir must render to a string")
    return rendered


def build_process_env(run_spec: RunSpec, context: Mapping[str, Any]) -> dict[str, str]:
    merged: dict[str, str] = dict(os.environ)
    profile = context.get("profile")
    if isinstance(profile, Mapping) and profile.get("env") is not None:
        if not isinstance(profile["env"], Mapping):
            raise V2ExecutionError("profile.env must be a mapping")
        _merge_env_map(merged, profile["env"], context, source_label="profile.env", render_values=False)
    _merge_env_map(merged, run_spec.env, context, source_label="run.env", render_values=True)
    return merged


def resolve_callable(doc: V2Document, callable_name: str) -> CommandDef | PipelineDef:
    if "." not in callable_name:
        resolved = doc.callables().get(callable_name)
    else:
        alias, nested_name = callable_name.split(".", 1)
        imported_doc = doc.imported_documents.get(alias)
        if imported_doc is None:
            raise V2ExecutionError(f"import alias '{alias}' not found for callable '{callable_name}'")
        resolved = imported_doc.callables().get(nested_name)
    if resolved is None:
        raise V2ExecutionError(f"callable '{callable_name}' not found")
    return resolved


def execute_command_def(
    command: CommandDef,
    *,
    context: Mapping[str, Any],
    step_name: str | None = None,
    doc: V2Document | None = None,
) -> StepResult:
    name = step_name or command.title or "command"
    if command.when is not None and not _evaluate_when(command.when, context):
        return _skipped(name)

    primary = execute_run_spec(command.run, context=context, step_name=name)
    if primary.status != StepStatus.FAILED or command.on_error is None:
        return primary
    if doc is None:
        raise V2ExecutionError("command.on_error execution requires document context")
    return _apply_on_error(owner=primary, on_error=command.on_error, doc=doc, context=context, owner_name=name)


def execute_pipeline_def(
    pipeline: PipelineDef,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    step_name: str | None = None,
) -> StepResult:
    name = step_name or pipeline.title or "pipeline"
    if pipeline.when is not None and not _evaluate_when(pipeline.when, context):
        return _skipped(name, with_children=True)

    started_at = _utcnow()
    start_perf = perf_counter()
    steps_state: dict[str, StepResult] = {}
    had_failure = False
    first_blocking_failure: StepResult | None = None

    for idx, raw_step in enumerate(pipeline.steps):
        pipeline_ctx = _with_steps(context, steps_state)
        step_result = execute_step(raw_step, doc=doc, context=pipeline_ctx, generated_name_index=idx)
        steps_state[step_result.name] = step_result

        if step_result.status == StepStatus.FAILED:
            had_failure = True
            if not normalize_step_spec(raw_step).continue_on_error:
                first_blocking_failure = step_result
                break

    result = StepResult(
        name=name,
        status=StepStatus.FAILED if had_failure else StepStatus.SUCCESS,
        duration_ms=_duration_ms(start_perf),
        started_at=started_at,
        finished_at=_utcnow(),
        children=steps_state,
        error=first_blocking_failure.error if first_blocking_failure else None,
    )

    if first_blocking_failure is not None and pipeline.on_error is not None:
        return _apply_on_error(owner=result, on_error=pipeline.on_error, doc=doc, context=_with_steps(context, steps_state), owner_name=name)
    return result


def execute_step(
    step: str | StepSpec,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
    generated_name_index: int = 0,
) -> StepResult:
    spec = normalize_step_spec(step)
    step_name = _step_name(step, spec, context, generated_name_index)
    step_ctx = _with_bindings(context, spec.with_values)

    if spec.when is not None and not _evaluate_when(spec.when, step_ctx):
        return _skipped(step_name)

    if spec.foreach is not None:
        foreach_result = execute_foreach_step(spec, doc=doc, context=step_ctx)
        foreach_result.name = step_name
        return foreach_result

    if spec.use is None:
        raise V2ExecutionError("step must define 'use' or 'foreach'")

    callable_def = resolve_callable(doc, spec.use)
    if isinstance(callable_def, PipelineDef):
        return execute_pipeline_def(callable_def, doc=doc, context=step_ctx, step_name=step_name)
    return execute_command_def(callable_def, context=step_ctx, step_name=step_name, doc=doc)


def execute_foreach_step(
    step: StepSpec,
    *,
    doc: V2Document,
    context: Mapping[str, Any],
) -> StepResult:
    if step.foreach is None:
        raise V2ExecutionError("execute_foreach_step requires foreach step")
    foreach = step.foreach

    items = render_scalar_or_ref(foreach.in_expr, context)
    if not isinstance(items, list):
        raise V2ExecutionError("foreach.in must render to list")

    started_at = _utcnow()
    start_perf = perf_counter()
    children: dict[str, StepResult] = {}
    failed_count = 0

    for index, item in enumerate(items):
        loop_ctx = {"index": index, "first": index == 0, "last": index == len(items) - 1}
        iter_ctx = dict(context)
        iter_ctx[foreach.as_name] = item
        iter_ctx["loop"] = loop_ctx

        iter_pipeline = PipelineDef(steps=foreach.steps)
        iter_name = f"iter_{index}"
        iter_result = execute_pipeline_def(iter_pipeline, doc=doc, context=iter_ctx, step_name=iter_name)
        children[iter_name] = iter_result
        if iter_result.status == StepStatus.FAILED:
            failed_count += 1

    return StepResult(
        name=step.step or "foreach",
        status=StepStatus.SUCCESS if failed_count == 0 else StepStatus.FAILED,
        duration_ms=_duration_ms(start_perf),
        started_at=started_at,
        finished_at=_utcnow(),
        children=children,
        meta={
            "iteration_count": len(items),
            "success_count": len(items) - failed_count,
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
    recovery_ctx = dict(context)
    recovery_ctx["error"] = dict(error_context)
    return execute_pipeline_def(
        PipelineDef(steps=on_error.steps),
        doc=doc,
        context=recovery_ctx,
        step_name=f"{owner_name}.on_error",
    )


def execute_run_spec(run_spec: RunSpec, *, context: Mapping[str, Any], step_name: str) -> StepResult:
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
            return StepResult(
                name=step_name,
                status=StepStatus.FAILED,
                stdout=_timeout_partial_output(exc.stdout, stdout_mode),
                stderr=_timeout_partial_output(exc.stderr, stderr_mode),
                duration_ms=_duration_ms(start_perf),
                started_at=started_at,
                finished_at=_utcnow(),
                error=ErrorContext(type="timeout", message=f"command timed out after {run_spec.timeout_ms} ms", step=step_name),
                meta={"program": program, "argv": argv, "workdir": workdir},
            )
        except FileNotFoundError as exc:
            raise V2ExecutionError(f"failed to start program '{program}': {exc}") from exc
        except OSError as exc:
            raise V2ExecutionError(f"OS error while starting program '{program}': {exc}") from exc

    status = StepStatus.SUCCESS if completed.returncode == 0 else StepStatus.FAILED
    error = None
    if status == StepStatus.FAILED:
        error = ErrorContext(
            type="command_failed",
            message=f"command exited with code {completed.returncode}",
            step=step_name,
            exit_code=completed.returncode,
        )
    return StepResult(
        name=step_name,
        status=status,
        exit_code=completed.returncode,
        stdout=completed.stdout if stdout_mode == "capture" else None,
        stderr=completed.stderr if stderr_mode == "capture" else None,
        duration_ms=_duration_ms(start_perf),
        started_at=started_at,
        finished_at=_utcnow(),
        error=error,
        meta={"program": program, "argv": argv, "workdir": workdir},
    )


def normalize_step_spec(step: str | StepSpec) -> StepSpec:
    return step if isinstance(step, StepSpec) else StepSpec(use=step)


def make_error_context(result: StepResult) -> dict[str, Any]:
    return {
        "step": result.error.step if result.error else result.name,
        "type": result.error.type if result.error else "execution_failed",
        "message": result.error.message if result.error else f"step '{result.name}' failed",
        "exit_code": result.error.exit_code if result.error else result.exit_code,
    }


def _apply_on_error(
    *, owner: StepResult, on_error: OnErrorSpec, doc: V2Document, context: Mapping[str, Any], owner_name: str
) -> StepResult:
    recovery = execute_on_error(on_error, doc=doc, context=context, error_context=make_error_context(owner), owner_name=owner_name)
    if recovery.status == StepStatus.SUCCESS:
        owner.status = StepStatus.RECOVERED
        owner.meta["on_error"] = {"status": "success", "result": recovery}
        return owner
    owner.status = StepStatus.FAILED
    owner.meta["recovery_error"] = {
        "message": recovery.error.message if recovery.error else "on_error failed",
        "status": recovery.status.value,
    }
    if owner.error is None:
        owner.error = ErrorContext(type="execution_failed", message="execution failed and on_error failed", step=owner_name)
    else:
        owner.error = ErrorContext(
            type=owner.error.type,
            message=f"{owner.error.message}; on_error failed",
            step=owner.error.step,
            exit_code=owner.error.exit_code,
        )
    return owner


def _step_name(original: str | StepSpec, spec: StepSpec, context: Mapping[str, Any], generated_name_index: int) -> str:
    if spec.step:
        return spec.step
    raw = spec.use or (original if isinstance(original, str) else "step")
    base = raw.split(".")[-1]
    steps = context.get("steps")
    if not isinstance(steps, Mapping) or base not in steps:
        return base
    suffix = 2
    while f"{base}_{suffix}" in steps:
        suffix += 1
    return f"{base}_{suffix}"


def _with_bindings(context: Mapping[str, Any], with_values: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(context)
    bindings = dict(merged.get("bindings") or {})
    for key, raw in with_values.items():
        value = render_scalar_or_ref(raw, context)
        bindings[key] = value
        merged[key] = value
    merged["bindings"] = bindings
    return merged


def _with_steps(context: Mapping[str, Any], steps_mapping: Mapping[str, StepResult]) -> dict[str, Any]:
    merged = dict(context)
    merged["steps"] = dict(steps_mapping)
    return merged


def _skipped(name: str, *, with_children: bool = False) -> StepResult:
    ts = _utcnow()
    return StepResult(
        name=name,
        status=StepStatus.SKIPPED,
        duration_ms=0,
        started_at=ts,
        finished_at=ts,
        children={} if with_children else {},
        meta={"reason": "when=false"},
    )


def _evaluate_when(when: Any, context: Mapping[str, Any]) -> bool:
    if isinstance(when, str) and when.strip().startswith("${") and when.strip().endswith("}"):
        return bool(evaluate_expression(when, context))
    return bool(render_scalar_or_ref(when, context))


def _merge_env_map(
    merged: dict[str, str], source: Mapping[str, Any], context: Mapping[str, Any], *, source_label: str, render_values: bool
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
    raise V2ExecutionError(f"{label} must render to scalar string/number/bool, got {type(value).__name__}")


def _parse_stream_mode(raw_mode: str | None, context: Mapping[str, Any], *, stream_name: str) -> tuple[str, str | None]:
    mode = raw_mode or "capture"
    if mode in ("capture", "inherit"):
        return mode, None
    if mode.startswith("file:"):
        rendered = render_string(mode[5:], context)
        if not isinstance(rendered, str) or not rendered:
            raise V2ExecutionError(f"{stream_name} file path must render to non-empty string")
        return "file", rendered
    raise V2ExecutionError(f"unsupported {stream_name} mode '{mode}', expected capture|inherit|file:<path>")


def _open_stream_target(stack: ExitStack, mode: str, target: str | None, stream_name: str):
    if mode == "capture":
        return subprocess.PIPE
    if mode == "inherit":
        return None
    if mode == "file":
        assert target is not None
        try:
            return stack.enter_context(open(target, "w", encoding="utf-8"))
        except OSError as exc:
            raise V2ExecutionError(f"failed to open {stream_name} file target '{target}': {exc}") from exc
    raise V2ExecutionError(f"internal unsupported stream mode '{mode}'")


def _timeout_partial_output(raw: Any, mode: str) -> str | None:
    if mode != "capture" or raw is None:
        return None
    return raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)


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
