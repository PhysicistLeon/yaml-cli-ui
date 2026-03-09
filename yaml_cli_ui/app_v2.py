"""Launcher-oriented Tkinter UI for YAML CLI UI v2.

AppV2Flow :=
  load v2 document
  choose profile
  render launchers
  open launcher dialog
  collect params
  apply launcher.with as fixed bindings
  execute callable in background
  render StepResult into logs/history/status
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .ui.form_widgets import FormValidationError, ParamForm
from .ui.history import RunHistory
from .ui.log_views import LogNotebook, render_step_result
from .ui.status import status_color
from .v2.context import build_runtime_context, context_to_mapping
from .v2.executor import execute_callable_name
from .v2.loader import load_v2_document
from .v2.models import ParamDef, ParamType, StepResult


def resolve_profile_ui_state(doc) -> tuple[bool, str | None, list[str]]:
    names = list(doc.profiles.keys())
    if not names:
        return False, None, []
    if len(names) == 1:
        return False, names[0], names
    return True, names[0], names


def launcher_param_plan(doc, launcher_name: str) -> tuple[dict[str, ParamDef], dict[str, Any]]:
    launcher = doc.launchers[launcher_name]
    fixed = dict(launcher.with_values)
    editable = {name: p for name, p in doc.params.items() if name not in fixed}
    return editable, fixed


class AppV2(tk.Tk):
    def __init__(self, config_path: str):
        super().__init__()
        self.title("YAML CLI UI v2")
        self.geometry("980x700")
        self.config_path = Path(config_path)
        self.doc = None
        self.history = RunHistory()
        self.launcher_buttons: dict[str, tk.Button] = {}
        self.launcher_infos: dict[str, str] = {}
        self.running_counts: dict[str, int] = {}
        self.profile_var = tk.StringVar(value="")

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="YAML file:").pack(side="left")
        self.path_entry = ttk.Entry(top)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.insert(0, str(self.config_path))
        ttk.Button(top, text="Reload", command=self.load_config).pack(side="left")

        self.profile_frame = ttk.Frame(self)
        self.profile_frame.pack(fill="x", padx=10, pady=(0, 6))

        launcher_row = ttk.Frame(self)
        launcher_row.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(launcher_row, text="Launchers:").pack(anchor="w")
        self.launchers_frame = ttk.Frame(launcher_row)
        self.launchers_frame.pack(fill="x", pady=(4, 0))

        self.output_notebook = ttk.Notebook(self)
        self.output_notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.logs = LogNotebook(self.output_notebook)

        self.load_config()

    def load_config(self) -> None:
        try:
            self.doc = load_v2_document(self.path_entry.get().strip())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Load error", str(exc), parent=self)
            return
        self._build_profile_selector()
        self._build_launcher_buttons()

    def _build_profile_selector(self) -> None:
        for child in self.profile_frame.winfo_children():
            child.destroy()
        assert self.doc is not None
        show_selector, selected, names = resolve_profile_ui_state(self.doc)
        if not names:
            self.profile_var.set("")
            return
        assert selected is not None
        self.profile_var.set(selected)
        if not show_selector:
            ttk.Label(self.profile_frame, text=f"Profile: {selected}").pack(anchor="w")
            return
        ttk.Label(self.profile_frame, text="Profile:").pack(side="left")
        combo = ttk.Combobox(self.profile_frame, state="readonly", values=names, textvariable=self.profile_var)
        combo.pack(side="left", padx=(6, 0))

    def _build_launcher_buttons(self) -> None:
        for child in self.launchers_frame.winfo_children():
            child.destroy()
        self.launcher_buttons.clear()
        self.launcher_infos.clear()
        assert self.doc is not None
        for idx, (name, launcher) in enumerate(self.doc.launchers.items()):
            btn = tk.Button(
                self.launchers_frame,
                text=launcher.title,
                bg=status_color("idle"),
                activebackground=status_color("idle"),
                command=lambda n=name: self.open_launcher_dialog(n),
            )
            btn.grid(row=idx // 4, column=idx % 4, sticky="ew", padx=4, pady=4)
            self.launcher_buttons[name] = btn
            self.launcher_infos[name] = launcher.info or ""
            self.logs.ensure_launcher_tab(name)

    def _editable_and_fixed_params(self, launcher_name: str) -> tuple[dict[str, ParamDef], dict[str, Any]]:
        assert self.doc is not None
        return launcher_param_plan(self.doc, launcher_name)

    def open_launcher_dialog(self, launcher_name: str) -> None:
        editable, fixed = self._editable_and_fixed_params(launcher_name)
        if not editable:
            self._start_launcher(launcher_name, params={})
            return

        dialog = tk.Toplevel(self)
        dialog.title(self.doc.launchers[launcher_name].title if self.doc else launcher_name)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("700x500")
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        form = ParamForm(body, params=editable | {k: self.doc.params[k] for k in fixed if k in self.doc.params}, fixed_values=fixed)

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=10, pady=(0, 10))

        def on_run() -> None:
            try:
                values = form.collect()
            except FormValidationError as exc:
                messagebox.showerror("Validation error", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._start_launcher(launcher_name, params=values)

        ttk.Button(actions, text="Run", command=on_run).pack(side="right")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))

    def _selected_profile_name(self) -> str | None:
        value = self.profile_var.get().strip()
        return value or None

    def _start_launcher(self, launcher_name: str, *, params: dict[str, Any]) -> None:
        run = self.history.start(launcher_name)
        self.running_counts[launcher_name] = self.running_counts.get(launcher_name, 0) + 1
        self._set_launcher_status(launcher_name, "running")
        self.logs.append(launcher_name, run.run_id, "Started")
        thread = threading.Thread(target=self._run_launcher_worker, args=(run.run_id, launcher_name, params), daemon=True)
        thread.start()

    def _set_launcher_status(self, launcher_name: str, status: str) -> None:
        btn = self.launcher_buttons.get(launcher_name)
        if btn is not None:
            color = status_color(status)
            btn.configure(bg=color, activebackground=color)

    def _run_launcher_worker(self, run_id: int, launcher_name: str, params: dict[str, Any]) -> None:
        assert self.doc is not None
        launcher = self.doc.launchers[launcher_name]
        try:
            result = run_launcher(self.doc, launcher_name=launcher_name, params=params, selected_profile_name=self._selected_profile_name())
            status = result.status.value
            secrets = _collect_secret_values(self.doc.params, params | launcher.with_values)
            rendered = render_step_result(result, secrets=secrets)
            self.after(0, self._finish_launcher_run, run_id, launcher_name, status, result, rendered, None)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._finish_launcher_run, run_id, launcher_name, "failed", None, "", str(exc))

    def _finish_launcher_run(self, run_id: int, launcher_name: str, status: str, result: StepResult | None, rendered_log: str, error: str | None) -> None:
        self.history.finish(run_id, status=status, result=result, payload={"log": rendered_log})
        if error:
            self.logs.append(launcher_name, run_id, f"[error] {error}")
            messagebox.showerror("Execution error", error, parent=self)
        else:
            self.logs.append(launcher_name, run_id, "Done")
            self.logs.append(launcher_name, run_id, rendered_log)

        self.running_counts[launcher_name] = max(0, self.running_counts.get(launcher_name, 1) - 1)
        if self.running_counts[launcher_name] > 0:
            self._set_launcher_status(launcher_name, "running")
        else:
            self._set_launcher_status(launcher_name, status)


def _collect_secret_values(params: dict[str, ParamDef], values: dict[str, Any]) -> list[str]:
    secrets: list[str] = []
    for name, param in params.items():
        if param.type != ParamType.SECRET:
            continue
        value = values.get(name)
        if isinstance(value, str) and value:
            secrets.append(value)
    return secrets


def run_launcher(doc, *, launcher_name: str, params: dict[str, Any], selected_profile_name: str | None = None) -> StepResult:
    launcher = doc.launchers[launcher_name]
    runtime = build_runtime_context(
        doc,
        params=params,
        selected_profile_name=selected_profile_name,
        with_values=launcher.with_values,
    )
    return execute_callable_name(
        launcher.use,
        doc=doc,
        context=context_to_mapping(runtime),
        step_name=launcher_name,
    )


def main_v2() -> None:
    parser = argparse.ArgumentParser(description="YAML-driven CLI UI v2")
    parser.add_argument("config")
    args = parser.parse_args()
    app = AppV2(args.config)
    app.mainloop()
