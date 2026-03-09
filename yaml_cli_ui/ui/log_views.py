"""Log notebook helpers and StepResult renderer for AppV2."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Iterable

from yaml_cli_ui.v2.models import StepResult


def render_step_result(result: StepResult, *, indent: int = 0, secrets: Iterable[str] = ()) -> str:
    pad = "  " * indent
    lines = [f"{pad}- {result.name}: {result.status.value}"]
    if result.exit_code is not None:
        lines.append(f"{pad}  exit_code: {result.exit_code}")
    if result.duration_ms is not None:
        lines.append(f"{pad}  duration_ms: {result.duration_ms}")
    if result.stdout:
        lines.append(f"{pad}  stdout: {_redact(result.stdout, secrets)}")
    if result.stderr:
        lines.append(f"{pad}  stderr: {_redact(result.stderr, secrets)}")
    if result.error is not None:
        lines.append(f"{pad}  error: {result.error.type}: {_redact(result.error.message, secrets)}")
    if result.meta:
        lines.append(f"{pad}  meta: {_redact(json.dumps(result.meta, ensure_ascii=False), secrets)}")
    for child in result.children.values():
        lines.append(render_step_result(child, indent=indent + 1, secrets=secrets))
    return "\n".join(lines)


def _redact(text: str, secrets: Iterable[str]) -> str:
    sanitized = text
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "******")
    return sanitized


class LogNotebook:
    def __init__(self, notebook: ttk.Notebook):
        self.notebook = notebook
        all_runs = ttk.Frame(self.notebook)
        self.notebook.add(all_runs, text="All runs")
        self.aggregate = tk.Text(all_runs, height=14)
        self.aggregate.pack(fill="both", expand=True)
        self.launcher_tabs: dict[str, tk.Text] = {}

    def ensure_launcher_tab(self, launcher: str) -> tk.Text:
        if launcher in self.launcher_tabs:
            return self.launcher_tabs[launcher]
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=launcher)
        output = tk.Text(tab, height=12)
        output.pack(fill="both", expand=True)
        self.launcher_tabs[launcher] = output
        return output

    def append(self, launcher: str, run_id: int, line: str) -> None:
        self.aggregate.insert("end", f"[{launcher}#{run_id}] {line}\n")
        self.aggregate.see("end")
        text = self.ensure_launcher_tab(launcher)
        text.insert("end", line + "\n")
        text.see("end")
