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
from tkinter import messagebox, simpledialog, ttk

from .ui.form_widgets import apply_values_to_v2_form, collect_v2_form_values, create_v2_form_fields
from .ui.history import RunHistoryStore
from .ui.log_views import map_step_status, render_step_result_text
from .ui.status import status_to_color
from .v2.context import build_runtime_context, context_to_mapping
from .v2.executor import execute_callable_name
from .v2.errors import V2Error
from .v2.loader import load_v2_document
from .v2.models import ParamDef, ParamType, SecretSource, StepResult, V2Document
from .v2.persistence import LauncherPersistenceService, V2PersistenceError


def resolve_profile_ui_state(doc: V2Document) -> tuple[bool, str | None, list[str]]:
    """Return profile selector state: (show_selector, selected_name, all_names)."""

    names = list(doc.profiles.keys())
    if not names:
        return False, None, []
    if len(names) == 1:
        return False, names[0], names
    return True, names[0], names


def launcher_param_plan(doc: V2Document, launcher_name: str) -> tuple[dict[str, ParamDef], dict[str, Any]]:
    """Conservative plan: editable root params minus launcher.with; fixed = launcher.with."""

    launcher = doc.launchers[launcher_name]
    fixed = dict(launcher.with_values)
    editable = {name: param for name, param in doc.params.items() if name not in fixed}
    return editable, fixed


def _param_has_ready_value(param: ParamDef) -> bool:
    if param.default is not None:
        return True
    if param.type != ParamType.SECRET:
        return False
    if param.source == SecretSource.ENV:
        return bool(param.env)
    if param.source == SecretSource.VAULT:
        return True
    return False


def run_launcher(
    doc: V2Document,
    launcher_name: str,
    params: dict[str, Any],
    *,
    selected_profile_name: str | None = None,
) -> StepResult:
    """Run launcher callable with merged params and short-name bindings from launcher.with.

    `launcher.with_values` is merged into `params` so callables see fixed values in
    `params` namespace; same map is also passed into `with_values` for bindings.
    """

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
        self.doc: V2Document | None = None
        self.history = RunHistoryStore()
        self.launcher_buttons: dict[str, tk.Button] = {}
        self.status_labels: dict[str, tk.Label] = {}
        self.log_widgets: dict[str, tk.Text] = {}
        self.history_vars: dict[str, tk.StringVar] = {}
        self.history_combos: dict[str, ttk.Combobox] = {}
        self.profile_var = tk.StringVar(value="")
        self.profile_combo: ttk.Combobox | None = None
        self.persistence: LauncherPersistenceService | None = None

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
        self.all_tab = ttk.Frame(self.output_notebook)
        self.output_notebook.add(self.all_tab, text="All runs")
        all_log = tk.Text(self.all_tab, wrap="word")
        all_log.pack(fill="both", expand=True)
        self.log_widgets["__all__"] = all_log

        self.reload()

    def reload(self) -> None:
        path = Path(self.path_var.get()).expanduser()
        self.doc = load_v2_document(path)
        self.persistence = LauncherPersistenceService(path, self.doc)
        if self.persistence.warnings:
            messagebox.showwarning("v2 persistence", "\n".join(self.persistence.warnings), parent=self)
        self._clear_launcher_views()
        self._render_profile_selector()
        self._render_launchers()

    def _clear_launcher_views(self) -> None:
        for tab_id in self.output_notebook.tabs()[1:]:
            self.output_notebook.forget(tab_id)
        self.launcher_buttons.clear()
        self.status_labels.clear()
        self.history_vars.clear()
        self.history_combos.clear()
        for name in list(self.log_widgets.keys()):
            if name != "__all__":
                del self.log_widgets[name]
        for child in self.launchers_frame.winfo_children():
            child.destroy()

    def _render_profile_selector(self) -> None:
        for child in self.profile_frame.winfo_children():
            child.destroy()
        assert self.doc is not None
        show_selector, selected, names = resolve_profile_ui_state(self.doc)
        preferred = self.persistence.get_selected_profile() if self.persistence else None
        if preferred in names:
            selected = preferred
        self.profile_combo = None
        self.profile_var.set(selected or "")

        if not names:
            return
        if not show_selector:
            ttk.Label(self.profile_frame, text=f"Profile: {selected}").pack(side="left")
            return

        ttk.Label(self.profile_frame, text="Profile").pack(side="left")
        combo = ttk.Combobox(
            self.profile_frame,
            values=names,
            textvariable=self.profile_var,
            state="readonly",
        )
        combo.current(names.index(self.profile_var.get()))
        combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        combo.pack(side="left", padx=8)
        self.profile_combo = combo

    def _render_launchers(self) -> None:
        assert self.doc is not None

        for name, launcher in self.doc.launchers.items():
            row = ttk.Frame(self.launchers_frame)
            row.pack(fill="x", pady=3)
            btn = tk.Button(row, text=launcher.title, command=lambda n=name: self.start_launcher(n))
            btn.pack(side="left")
            ttk.Label(row, text=launcher.info or "").pack(side="left", padx=8)
            status = tk.Label(row, text=" idle ", bg=status_to_color("idle"))
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
        editable, fixed = launcher_param_plan(self.doc, launcher_name)

        last_values = self.persistence.get_last_values(launcher_name) if self.persistence else {}
        initial_values = {k: v for k, v in last_values.items() if k in editable}
        needs_dialog = any(not _param_has_ready_value(param) for param in editable.values())
        if not needs_dialog:
            self._execute_in_background(launcher_name, {})
            return

        launcher = self.doc.launchers[launcher_name]
        dialog = tk.Toplevel(self)
        dialog.title(launcher.title)
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        preset_var = tk.StringVar(value="")
        preset_combo: ttk.Combobox | None = None

        preset_names = self.persistence.list_presets(launcher_name) if self.persistence else []
        if preset_names:
            preset_frame = ttk.Frame(body)
            preset_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            ttk.Label(preset_frame, text="Preset").pack(side="left")
            preset_combo = ttk.Combobox(preset_frame, values=preset_names, textvariable=preset_var, state="readonly")
            preset_combo.pack(side="left", fill="x", expand=True, padx=6)

        fields = create_v2_form_fields(body, editable, initial_values=initial_values, fixed_values=fixed)

        def apply_selected_preset() -> None:
            if not self.persistence:
                return
            name = preset_var.get().strip()
            if not name:
                return
            preset = self.persistence.get_preset(launcher_name, name) or {}
            filtered = {k: v for k, v in preset.items() if k in editable}
            apply_values_to_v2_form(fields, filtered)

        if preset_combo is not None:
            preset_combo.bind("<<ComboboxSelected>>", lambda _e: apply_selected_preset())
            last_selected = self.persistence.get_last_selected_preset(launcher_name) if self.persistence else None
            if last_selected and last_selected in preset_names:
                preset_var.set(last_selected)
                apply_selected_preset()

        def persist_current_as_preset(overwrite: bool = False) -> None:
            if not self.persistence:
                return
            values, errors = collect_v2_form_values(fields)
            if errors:
                messagebox.showerror("Validation error", "\n".join(errors), parent=dialog)
                return
            existing = self.persistence.list_presets(launcher_name)
            chosen = preset_var.get().strip() if overwrite else ""
            if not chosen:
                chosen = simpledialog.askstring("Preset name", "Name for preset", parent=dialog) or ""
            chosen = chosen.strip()
            if not chosen:
                return
            if not overwrite and chosen in existing:
                messagebox.showerror("Preset exists", "Preset with this name already exists", parent=dialog)
                return
            self.persistence.upsert_preset(launcher_name, chosen, values)
            preset_var.set(chosen)
            if preset_combo is not None:
                preset_combo["values"] = self.persistence.list_presets(launcher_name)

        def rename_selected_preset() -> None:
            if not self.persistence:
                return
            current = preset_var.get().strip()
            if not current:
                return
            new_name = simpledialog.askstring("Rename preset", "New preset name", parent=dialog) or ""
            new_name = new_name.strip()
            if not new_name:
                return
            self.persistence.rename_preset(launcher_name, current, new_name)
            preset_var.set(new_name)
            if preset_combo is not None:
                preset_combo["values"] = self.persistence.list_presets(launcher_name)

        def delete_selected_preset() -> None:
            if not self.persistence:
                return
            current = preset_var.get().strip()
            if not current:
                return
            self.persistence.delete_preset(launcher_name, current)
            preset_var.set("")
            if preset_combo is not None:
                preset_combo["values"] = self.persistence.list_presets(launcher_name)

        def on_run() -> None:
            values, errors = collect_v2_form_values(fields)
            if errors:
                messagebox.showerror("Validation error", "\n".join(errors), parent=dialog)
                return
            if self.persistence:
                self.persistence.set_last_values(launcher_name, values)
                selected_preset = preset_var.get().strip() or None
                self.persistence.set_last_selected_preset(launcher_name, selected_preset)
            dialog.destroy()
            self._execute_in_background(launcher_name, values)

        footer = ttk.Frame(dialog)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(footer, text="Run", command=on_run).pack(side="right")
        ttk.Button(footer, text="Save preset", command=lambda: persist_current_as_preset(False)).pack(side="left")
        ttk.Button(footer, text="Overwrite", command=lambda: persist_current_as_preset(True)).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="Rename", command=rename_selected_preset).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="Delete", command=delete_selected_preset).pack(side="left", padx=(6, 0))

    def _on_profile_selected(self, _event: object | None = None) -> None:
        if self.persistence:
            try:
                self.persistence.set_selected_profile(self.profile_var.get() or None)
            except V2PersistenceError as exc:
                messagebox.showwarning("v2 persistence", str(exc), parent=self)

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
                text = render_step_result_text(
                    result,
                    secret_values=self._secret_values(values, launcher_name),
                )
                self.after(0, self._complete_run, rec.run_id, launcher_name, status, result, text)
            except (V2Error, OSError, ValueError, TypeError, RuntimeError) as exc:
                self.after(0, self._complete_run, rec.run_id, launcher_name, "failed", None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _secret_values(self, values: dict[str, Any], launcher_name: str) -> list[str]:
        assert self.doc is not None
        launcher = self.doc.launchers[launcher_name]
        merged = dict(values)
        merged.update(launcher.with_values)
        return [
            str(merged[name])
            for name, param in self.doc.params.items()
            if param.type == ParamType.SECRET and name in merged and merged[name]
        ]

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
        label.configure(text=f" {status} ", bg=status_to_color(status))

    def _append_log(self, tab: str, text: str) -> None:
        w = self.log_widgets[tab]
        w.insert("end", text + "\n")
        w.see("end")
