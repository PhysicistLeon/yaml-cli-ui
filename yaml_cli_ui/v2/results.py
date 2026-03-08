"""Execution result aliases for YAML CLI UI v2 scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import StepResult, StepStatus


@dataclass(slots=True)
class PipelineResult:
    """Aggregated runtime result for a pipeline call."""

    name: str
    steps: list[StepResult] = field(default_factory=list)


__all__ = ["PipelineResult", "StepResult", "StepStatus"]
