"""In-memory run history store for AppV2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from yaml_cli_ui.v2.models import StepResult


@dataclass
class RunRecord:
    run_id: int
    launcher: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    result: StepResult | None = None
    log_text: str = ""


@dataclass
class RunHistoryStore:
    seq: int = 0
    records: dict[int, RunRecord] = field(default_factory=dict)
    by_launcher: dict[str, list[int]] = field(default_factory=dict)

    def create(self, launcher: str) -> RunRecord:
        self.seq += 1
        rec = RunRecord(run_id=self.seq, launcher=launcher, status="running", started_at=datetime.now())
        self.records[rec.run_id] = rec
        self.by_launcher.setdefault(launcher, []).append(rec.run_id)
        return rec

    def finish(self, run_id: int, *, status: str, result: StepResult | None, log_text: str) -> RunRecord:
        rec = self.records[run_id]
        rec.status = status
        rec.result = result
        rec.log_text = log_text
        rec.ended_at = datetime.now()
        return rec

    def labels_for(self, launcher: str) -> list[str]:
        labels: list[str] = []
        for rid in self.by_launcher.get(launcher, []):
            rec = self.records[rid]
            labels.append(f"#{rec.run_id} [{rec.started_at.strftime('%H:%M:%S')}] {rec.status}")
        return labels
