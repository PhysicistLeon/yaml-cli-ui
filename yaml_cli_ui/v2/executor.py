"""Execution engine scaffold for YAML CLI UI v2."""

from __future__ import annotations

from .models import RunContext, V2Document
from .results import PipelineResult


def execute_launcher(doc: V2Document, launcher_name: str, context: RunContext) -> PipelineResult:
    """Execute launcher target in v2 runtime (placeholder)."""

    raise NotImplementedError(
        "v2 executor is intentionally deferred in migration scaffold"
    )
