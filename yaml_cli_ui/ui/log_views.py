"""Text log rendering helpers for run results."""

from __future__ import annotations

from yaml_cli_ui.v2.models import StepResult, StepStatus


def map_step_status(result: StepResult) -> str:
    status = result.status
    if status == StepStatus.SUCCESS:
        return "success"
    if status == StepStatus.RECOVERED:
        return "recovered"
    if status == StepStatus.FAILED:
        return "failed"
    if status == StepStatus.SKIPPED:
        return "idle"
    return "idle"


def _redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "******")
    return redacted


def render_step_result_text(result: StepResult, *, secret_values: list[str] | None = None) -> str:
    lines: list[str] = []
    _render(result, lines, 0)
    rendered = "\n".join(lines)
    return _redact(rendered, secret_values or [])


def _render(result: StepResult, lines: list[str], depth: int) -> None:
    prefix = "  " * depth
    line = f"{prefix}- {result.name}: {result.status.value}"
    if result.exit_code is not None:
        line += f" (exit_code={result.exit_code})"
    if result.duration_ms is not None:
        line += f" [{result.duration_ms}ms]"
    lines.append(line)

    if result.stdout:
        lines.append(f"{prefix}  stdout: {result.stdout.strip()}")
    if result.stderr:
        lines.append(f"{prefix}  stderr: {result.stderr.strip()}")
    if result.error is not None:
        lines.append(f"{prefix}  error: {result.error.type}: {result.error.message}")

    foreach_meta = result.meta if isinstance(result.meta, dict) else {}
    if "iteration_count" in foreach_meta:
        lines.append(
            f"{prefix}  foreach: iterations={foreach_meta.get('iteration_count')} "
            f"ok={foreach_meta.get('success_count')} failed={foreach_meta.get('failed_count')}"
        )

    for child_name in sorted(result.children):
        _render(result.children[child_name], lines, depth + 1)
