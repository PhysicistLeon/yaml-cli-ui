"""Launcher-oriented Tk app for YAML CLI UI v2.

AppV2Flow :=
  load v2 document
  choose profile
  render launchers
  open launcher dialog
  collect params
  apply launcher.with as fixed bindings
  execute callable in background
  render StepResult into logs/history/status

LauncherDialog :=
  editable params
  fixed/read-only with-bound params
  validation
  submit -> background execution
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import messagebox, ttk

from .ui.form_widgets import collect_v2_form_values, create_v2_form_fields
from .ui.history import RunHistoryStore
from .ui.log_views import map_step_status, render_step_result_text
from .ui.status import status_to_color
from .v2.context import build_runtime_context, context_to_mapping
from .v2.executor import execute_callable_name
from .v2.loader import load_v2_document
from .v2.models import StepResult, V2Document


def run_launcher(
    doc: V2Document,
    launcher_name: str,
    params: dict[str, Any],
    *,
    selected_profile_name: str | None = None,
) -> StepResult:
    launcher = doc.launchers[launcher_name]
    merged_params = dict(params)
    merged_params.update(launcher.with_values)
    run_context = build_runtime_context(
        doc,
        params=merged_params,
        selected_profile_name=selected_profile_name,
        with_values=launcher.with_values,
    )
    return execute_callable_name(
        launcher.use,
        doc=doc,
        context=context_to_mapping(run_context),
        step_name=launcher_name,
    )


class AppV2(tk.Tk):
    def __init__(self, config_path: str):
        super().__init__()
        self.title("YAML CLI UI v2")
        self.geometry("1000x700")
        self.config_path = config_path
        self.doc: V2Document | None = None
        self.history = RunHistoryStore()
        self.launcher_buttons: dict[str, tk.Button] = {}
        self.status_labels: dict[str, ttk.Label] = {}
        self.log_widgets: dict[str, tk.Text] = {}
        self.history_vars: dict[str, tk.StringVar] = {}
        self.history_combos: dict[str, ttk.Combobox] = {}
        self.profile_var = tk.StringVar(value="")
        self.profile_combo: ttk.Combobox | None = None

        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=10)
        ttk.Label(header, text="Config").pack(side="left")
        self.path_var = tk.StringVar(value=config_path)
        ttk.Entry(header, textvariable=self.path_var, width=90).pack(side="left", padx=8)
        ttk.Button(header, text="Reload", command=self.reload).pack(side="left")

        self.profile_frame = ttk.Frame(self)
        self.profile_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.launchers_frame = ttk.Frame(self)
        self.launchers_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.output_notebook = ttk.Notebook(self)
        self.output_notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        all_tab = ttk.Frame(self.output_notebook)
        self.output_notebook.add(all_tab, text="All runs")
        all_log = tk.Text(all_tab, wrap="word")
        all_log.pack(fill="both", expand=True)
        self.log_widgets["__all__"] = all_log

        self.reload()

    def reload(self) -> None:
        path = Path(self.path_var.get()).expanduser()
        self.doc = load_v2_document(path)
        self._render_profile_selector()
        self._render_launchers()

    def _render_profile_selector(self) -> None:
        for child in self.profile_frame.winfo_children():
            child.destroy()
        assert self.doc is not None
        names = list(self.doc.profiles.keys())
        self.profile_combo = None
        if not names:
            self.profile_var.set("")
            return
        if len(names) == 1:
            self.profile_var.set(names[0])
            ttk.Label(self.profile_frame, text=f"Profile: {names[0]}").pack(side="left")
            return
        ttk.Label(self.profile_frame, text="Profile").pack(side="left")
        combo = ttk.Combobox(self.profile_frame, values=names, textvariable=self.profile_var, state="readonly")
        combo.current(0)
        combo.pack(side="left", padx=8)
        self.profile_combo = combo

    def _render_launchers(self) -> None:
        for child in self.launchers_frame.winfo_children():
            child.destroy()
        assert self.doc is not None
        self.launcher_buttons.clear()
        self.status_labels.clear()

        for name, launcher in self.doc.launchers.items():
            row = ttk.Frame(self.launchers_frame)
            row.pack(fill="x", pady=3)
            btn = tk.Button(row, text=launcher.title, command=lambda n=name: self.start_launcher(n))
            btn.pack(side="left")
            info = launcher.info or ""
            ttk.Label(row, text=info).pack(side="left", padx=8)
            status = ttk.Label(row, text="idle", background=status_to_color("idle"))
            status.pack(side="right")
            self.launcher_buttons[name] = btn
            self.status_labels[name] = status

            tab = ttk.Frame(self.output_notebook)
            self.output_notebook.add(tab, text=name)
            top = ttk.Frame(tab)
            top.pack(fill="x")
            var = tk.StringVar(value="")
            combo = ttk.Combobox(top, textvariable=var, state="readonly")
            combo.pack(side="left", fill="x", expand=True, padx=6, pady=4)
            combo.bind("<<ComboboxSelected>>", lambda _e, n=name: self._on_history_selected(n))
            text = tk.Text(tab, wrap="word")
            text.pack(fill="both", expand=True)
            self.log_widgets[name] = text
            self.history_vars[name] = var
            self.history_combos[name] = combo

    def start_launcher(self, launcher_name: str) -> None:
        assert self.doc is not None
        launcher = self.doc.launchers[launcher_name]
        editable = {k: p for k, p in self.doc.params.items() if k not in launcher.with_values}
        fixed = dict(launcher.with_values)

        requires_input = any(
            p.required and p.default is None for p in editable.values()
        ) or bool(editable)
        if not requires_input:
            self._execute_in_background(launcher_name, {})
            return

        dialog = tk.Toplevel(self)
        dialog.title(launcher.title)
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        fields = create_v2_form_fields(body, editable, fixed_values=fixed)

        def on_run() -> None:
            values, errors = collect_v2_form_values(fields)
            if errors:
                messagebox.showerror("Validation error", "\n".join(errors), parent=dialog)
                return
            dialog.destroy()
            self._execute_in_background(launcher_name, values)

        footer = ttk.Frame(dialog)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(footer, text="Run", command=on_run).pack(side="right")

    def _execute_in_background(self, launcher_name: str, values: dict[str, Any]) -> None:
        rec = self.history.create(launcher_name)
        self._set_status(launcher_name, "running")
        self._append_log("__all__", f"[{launcher_name}#{rec.run_id}] started")

        def worker() -> None:
            assert self.doc is not None
            try:
                result = run_launcher(
                    self.doc,
                    launcher_name,
                    values,
                    selected_profile_name=(self.profile_var.get() or None),
                )
                status = map_step_status(result)
                text = render_step_result_text(result, secret_values=self._secret_values(values, launcher_name))
                self.after(0, self._complete_run, rec.run_id, launcher_name, status, result, text)
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._complete_run, rec.run_id, launcher_name, "failed", None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _secret_values(self, values: dict[str, Any], launcher_name: str) -> list[str]:
        assert self.doc is not None
        launcher = self.doc.launchers[launcher_name]
        merged = dict(values)
        merged.update(launcher.with_values)
        secrets: list[str] = []
        for name, param in self.doc.params.items():
            if param.type.value == "secret" and name in merged and merged[name]:
                secrets.append(str(merged[name]))
        return secrets

    def _complete_run(
        self,
        run_id: int,
        launcher_name: str,
        status: str,
        result: StepResult | None,
        text: str,
    ) -> None:
        self.history.finish(run_id, status=status, result=result, log_text=text)
        self._set_status(launcher_name, status)
        self._append_log("__all__", f"[{launcher_name}#{run_id}] {status}\n{text}\n")
        self._append_log(launcher_name, text)
        self._refresh_history(launcher_name)

    def _refresh_history(self, launcher_name: str) -> None:
        labels = self.history.labels_for(launcher_name)
        combo = self.history_combos[launcher_name]
        combo["values"] = labels
        if labels:
            self.history_vars[launcher_name].set(labels[-1])

    def _on_history_selected(self, launcher_name: str) -> None:
        label = self.history_vars[launcher_name].get()
        for run_id in self.history.by_launcher.get(launcher_name, []):
            rec = self.history.records[run_id]
            if label.startswith(f"#{run_id} "):
                self.log_widgets[launcher_name].delete("1.0", "end")
                self.log_widgets[launcher_name].insert("end", rec.log_text)

    def _set_status(self, launcher_name: str, status: str) -> None:
        label = self.status_labels[launcher_name]
        label.configure(text=status, background=status_to_color(status))

    def _append_log(self, tab: str, text: str) -> None:
        w = self.log_widgets[tab]
        w.insert("end", text + "\n")
        w.see("end")
