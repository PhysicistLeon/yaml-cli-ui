"""In-memory run history for AppV2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from yaml_cli_ui.v2.models import StepResult


@dataclass
class RunRecord:
    run_id: int
    launcher: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    result: StepResult | None = None
    lines: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


class RunHistory:
    def __init__(self) -> None:
        self._seq = 0
        self.records: dict[int, RunRecord] = {}
        self.by_launcher: dict[str, list[int]] = {}

    def start(self, launcher: str) -> RunRecord:
        self._seq += 1
        run = RunRecord(
            run_id=self._seq,
            launcher=launcher,
            status="running",
            started_at=datetime.now(),
        )
        self.records[run.run_id] = run
        self.by_launcher.setdefault(launcher, []).append(run.run_id)
        return run

    def finish(self, run_id: int, *, status: str, result: StepResult | None, payload: dict[str, Any] | None = None) -> RunRecord:
        run = self.records[run_id]
        run.status = status
        run.result = result
        run.ended_at = datetime.now()
        if payload:
            run.payload.update(payload)
        return run

    def label(self, run_id: int) -> str:
        run = self.records[run_id]
        return f"#{run.run_id} [{run.started_at.strftime('%H:%M:%S')}] {run.status}"
