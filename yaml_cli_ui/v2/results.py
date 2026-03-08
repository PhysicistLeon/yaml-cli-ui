"""Execution result models for YAML CLI UI v2 scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StepStatus(str, Enum):
    """Status of a step execution in v2."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


@dataclass(slots=True)
class StepResult:
    """Runtime result for a single executed step."""

    status: StepStatus
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class PipelineResult:
    """Aggregated runtime result for a pipeline call."""

    name: str
    steps: list[StepResult] = field(default_factory=list)
