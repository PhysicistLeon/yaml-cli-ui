"""Shared status presentation helpers for Tkinter UI variants."""

from __future__ import annotations

IDLE_COLOR = "#d9d9d9"
RUNNING_COLOR = "#f1c40f"
SUCCESS_COLOR = "#2ecc71"
FAILED_COLOR = "#e74c3c"
RECOVERED_COLOR = "#f39c12"

STATUS_COLORS = {
    "idle": IDLE_COLOR,
    "running": RUNNING_COLOR,
    "success": SUCCESS_COLOR,
    "failed": FAILED_COLOR,
    "recovered": RECOVERED_COLOR,
    "skipped": IDLE_COLOR,
}


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, IDLE_COLOR)
