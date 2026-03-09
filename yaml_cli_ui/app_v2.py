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

Launcher UX :=
  launcher.info is displayed via hover tooltip (no inline label)
  launcher dialog includes only params used by selected launcher graph
  launcher starts immediately only when selected launcher uses no root params

Param materialization precedence for launcher execution:
  root defaults -> persisted last_values -> selected preset -> user-entered -> launcher.with
`launcher.with` remains the final fixed override.
"""

from __future__ import annotations

import argparse
import re
import threading
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .settings import load_launch_settings
from .bootstrap import detect_yaml_version, open_app_for_config
from .ui.form_widgets import apply_values_to_v2_form, collect_v2_form_values, create_v2_form_fields
from .ui.history import RunHistoryStore
from .ui.log_views import map_step_status, render_step_result_text
from .ui.status import status_to_color
from .ui.tooltips import TooltipController, attach_tooltip
from .v2.context import build_runtime_context, context_to_mapping
from .v2.executor import execute_callable_name
from .v2.errors import V2Error
from .v2.loader import load_v2_document
from .v2.models import ParamDef, ParamType, StepResult, V2Document
from .v2.persistence import LauncherPersistenceService


DEFAULT_CONFIG_PATH = "examples/yt_audio.yaml"
_PARAM_REF_PATTERN = re.compile(r"\$params\.([A-Za-z_][A-Za-z0-9_]*)|\$\{params\.([A-Za-z_][A-Za-z0-9_]*)[^}]*\}")
_SHORT_REF_PATTERN = re.compile(r"^\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)\}?$")


def resolve_profile_ui_state(doc: V2Document) -> tuple[bool, str | None, list[str]]:
    """Return profile selector state: (show_selector, selected_name, all_names)."""

    names = list(doc.profiles.keys())
    if not names:
        return False, None, []
    if len(names) == 1:
        return False, names[0], names
    return True, names[0], names


def _collect_param_refs_from_value(value: Any, available_params: set[str]) -> set[str]:
    used: set[str] = set()
    if isinstance(value, str):
        for direct, templated in _PARAM_REF_PATTERN.findall(value):
            if direct:
                used.add(direct)
            if templated:
                used.add(templated)
        short = _SHORT_REF_PATTERN.match(value.strip())
        if short and short.group(1) in available_params:
            used.add(short.group(1))
        return used
    if isinstance(value, dict):
        for nested in value.values():
            used.update(_collect_param_refs_from_value(nested, available_params))
    elif isinstance(value, list):
        for nested in value:
            used.update(_collect_param_refs_from_value(nested, available_params))
    return used


def _resolve_callable_for_analysis(
    doc: V2Document,
    callable_name: str,
) -> tuple[V2Document, Any] | None:
    if "." in callable_name:
        alias, nested = callable_name.split(".", 1)
        imported_doc = doc.imported_documents.get(alias)
        if imported_doc is None:
            return None
        return _resolve_callable_for_analysis(imported_doc, nested)
    callable_obj = doc.callables().get(callable_name)
    if callable_obj is None:
        return None
    return doc, callable_obj


def collect_used_params_for_launcher(doc: V2Document, launcher_name: str) -> set[str]:
    """Collect root params referenced by launcher target graph."""

    available_params = set(doc.params.keys())
    used: set[str] = set()
    visited: set[tuple[int, str]] = set()

    def collect_callable(target_doc: V2Document, callable_name: str) -> None:
        key = (id(target_doc), callable_name)
        if key in visited:
            return
        visited.add(key)

        resolved = _resolve_callable_for_analysis(target_doc, callable_name)
        if resolved is None:
            return
        resolved_doc, callable_obj = resolved
        used.update(_collect_param_refs_from_value(callable_obj.when, available_params))

        if hasattr(callable_obj, "run"):
            run = callable_obj.run
            used.update(_collect_param_refs_from_value(run.program, available_params))
            used.update(_collect_param_refs_from_value(run.argv, available_params))
            used.update(_collect_param_refs_from_value(run.workdir, available_params))
            used.update(_collect_param_refs_from_value(run.env, available_params))
        else:
            for step in callable_obj.steps:
                collect_step(resolved_doc, step)

        if callable_obj.on_error is not None:
            for fallback in callable_obj.on_error.steps:
                collect_step(resolved_doc, fallback)

    def collect_step(target_doc: V2Document, step: Any) -> None:
        if isinstance(step, str):
            collect_callable(target_doc, step)
            return
        used.update(_collect_param_refs_from_value(step.when, available_params))
        if step.foreach is not None:
            used.update(_collect_param_refs_from_value(step.foreach.in_expr, available_params))
            for nested_step in step.foreach.steps:
                collect_step(target_doc, nested_step)
            return
        used.update(_collect_param_refs_from_value(step.with_values, available_params))
        if step.use:
            collect_callable(target_doc, step.use)

    launcher = doc.launchers[launcher_name]
    used.update(_collect_param_refs_from_value(doc.locals, available_params))
    used.update(_collect_param_refs_from_value(launcher.with_values, available_params))
    collect_callable(doc, launcher.use)
    return used


def launcher_param_plan(doc: V2Document, launcher_name: str) -> tuple[dict[str, ParamDef], dict[str, Any]]:
    """Return launcher dialog plan with only used params and fixed launcher.with values."""

    launcher = doc.launchers[launcher_name]
    used_params = collect_used_params_for_launcher(doc, launcher_name)
    fixed = {name: value for name, value in launcher.with_values.items() if name in used_params}
    editable = {
        name: param
        for name, param in doc.params.items()
        if name in used_params and name not in fixed
    }
    return editable, fixed


def has_effective_initial_value(value: Any) -> bool:
    """Return whether dialog field has a meaningful prefilled value."""

    return value not in (None, "", [], {})


def order_editable_params_for_dialog(
    editable: dict[str, ParamDef],
    initial_values: dict[str, Any] | None = None,
) -> dict[str, ParamDef]:
    """Stable-partition launcher fields: empty editable first, prefilled second.

    Defaults/state/presets only prefill values and never hide fields. Ordering keeps
    original YAML declaration order inside each group.
    """

    initial_values = initial_values or {}
    empty: list[tuple[str, ParamDef]] = []
    prefilled: list[tuple[str, ParamDef]] = []
    for name, param in editable.items():
        effective_value = initial_values.get(name, param.default)
        target = prefilled if has_effective_initial_value(effective_value) else empty
        target.append((name, param))
    return dict([*empty, *prefilled])


def should_open_launcher_dialog(editable: dict[str, ParamDef], fixed: dict[str, Any]) -> bool:
    """Return True when launcher dialog should be shown before execution.

    Defaults, persisted state, and presets only prefill form values and never suppress
    the dialog. `launcher.with` values remain fixed/read-only but still count as used
    params for dialog gating. The dialog is skipped only when launcher execution graph
    uses no root params at all.
    """

    return bool(editable or fixed)


def run_launcher(
    doc: V2Document,
    launcher_name: str,
    params: dict[str, Any],
    *,
    selected_profile_name: str | None = None,
    state_values: dict[str, Any] | None = None,
    preset_values: dict[str, Any] | None = None,
) -> StepResult:
    """Run launcher callable with merged params and short-name bindings from launcher.with.

    `launcher.with_values` is merged into `params` so callables see fixed values in
    `params` namespace; same map is also passed into `with_values` for bindings.
    """

    launcher = doc.launchers[launcher_name]
    merged_params = materialize_launcher_params(
        doc,
        launcher_name,
        state_values=state_values,
        preset_values=preset_values,
        user_values=params,
    )
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


def _default_materialized_params(doc: V2Document) -> dict[str, Any]:
    """Build root param defaults available without explicit user input."""

    result: dict[str, Any] = {}
    for name, param in doc.params.items():
        if param.default is not None:
            result[name] = param.default
    return result


def materialize_launcher_params(
    doc: V2Document,
    launcher_name: str,
    *,
    state_values: dict[str, Any] | None = None,
    preset_values: dict[str, Any] | None = None,
    user_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize final launcher params with deterministic precedence."""

    known = set(doc.params.keys())

    def _known_only(values: dict[str, Any] | None) -> dict[str, Any]:
        if not values:
            return {}
        return {name: value for name, value in values.items() if name in known}

    merged = _default_materialized_params(doc)
    merged.update(_known_only(state_values))
    merged.update(_known_only(preset_values))
    merged.update(_known_only(user_values))
    merged.update(doc.launchers[launcher_name].with_values)
    return merged


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
        self.tooltip = TooltipController(self)

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
        if detect_yaml_version(path) != 2:
            replacement = open_app_for_config(path)
            self.destroy()
            replacement.mainloop()
            return

        self.doc = load_v2_document(path)
        self.persistence = LauncherPersistenceService(path, self.doc)
        self.persistence.load_presets()
        self.persistence.load_state()
        if self.persistence.warnings:
            unique_warnings = list(dict.fromkeys(self.persistence.warnings))
            messagebox.showwarning(
                "Persistence warning",
                "Using safe defaults for v2 persistence due to errors\n\n"
                + "\n".join(unique_warnings),
                parent=self,
            )
        self._clear_launcher_views()
        self._render_profile_selector()
        self._render_launchers()

    def _clear_launcher_views(self) -> None:
        self.tooltip.hide()
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
        saved = self.persistence.get_selected_profile() if self.persistence else None
        if saved and saved in names:
            selected = saved
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
        combo.current(0)
        if selected in names:
            combo.current(names.index(selected))
        combo.bind("<<ComboboxSelected>>", self._on_profile_changed)
        combo.pack(side="left", padx=8)
        self.profile_combo = combo

    def _on_profile_changed(self, _event: tk.Event[Any]) -> None:
        if not self.persistence:
            return
        selected = self.profile_var.get() or None
        self.persistence.set_selected_profile(selected)

    def _render_launchers(self) -> None:
        assert self.doc is not None

        for name, launcher in self.doc.launchers.items():
            row = ttk.Frame(self.launchers_frame)
            row.pack(fill="x", pady=3)
            btn = tk.Button(row, text=launcher.title, command=lambda n=name: self.start_launcher(n))
            btn.pack(side="left")
            attach_tooltip(self.tooltip, btn, launcher.info)
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

        if not should_open_launcher_dialog(editable, fixed):
            self._execute_in_background(launcher_name, {})
            return

        launcher = self.doc.launchers[launcher_name]
        dialog = tk.Toplevel(self)
        dialog.title(launcher.title)
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        initial_values: dict[str, Any] = {}
        selected_preset_var = tk.StringVar(value="")
        preset_values: dict[str, Any] = {}
        if self.persistence:
            initial_values.update(self.persistence.get_last_values(launcher_name))
            last_preset = self.persistence.get_last_selected_preset(launcher_name)
            if last_preset:
                selected_preset_var.set(last_preset)
                preset_values = self.persistence.apply_preset_values(launcher_name, last_preset)
                initial_values.update(preset_values)
        ordered_editable = order_editable_params_for_dialog(editable, initial_values)
        fields = create_v2_form_fields(body, ordered_editable, initial_values=initial_values, fixed_values=fixed)

        presets_row = ttk.Frame(body)
        presets_row.grid(row=len(ordered_editable), column=0, columnspan=2, sticky="ew", padx=5, pady=(8, 2))
        ttk.Label(presets_row, text="Preset").pack(side="left")
        preset_combo = ttk.Combobox(presets_row, textvariable=selected_preset_var, state="readonly")
        preset_combo.pack(side="left", fill="x", expand=True, padx=6)

        def refresh_presets() -> None:
            if not self.persistence:
                preset_combo["values"] = []
                return
            values = self.persistence.list_presets(launcher_name)
            preset_combo["values"] = values
            if selected_preset_var.get() and selected_preset_var.get() not in values:
                selected_preset_var.set("")

        def on_select_preset(_event: tk.Event[Any] | None = None) -> None:
            if not self.persistence:
                return
            name = selected_preset_var.get()
            values = self.persistence.apply_preset_values(launcher_name, name)
            if not values:
                return
            apply_values_to_v2_form(fields, values)

        def save_preset(overwrite: bool) -> None:
            if not self.persistence:
                return
            current = selected_preset_var.get().strip()
            if not current or not overwrite:
                asked = simpledialog.askstring("Save preset", "Preset name:", parent=dialog)
                if not asked:
                    return
                current = asked.strip()
                if not current:
                    return
            values, errors = collect_v2_form_values(fields)
            if errors:
                messagebox.showerror("Validation error", "\n".join(errors), parent=dialog)
                return
            self.persistence.upsert_preset(launcher_name, current, values)
            selected_preset_var.set(current)
            refresh_presets()

        def rename_preset() -> None:
            if not self.persistence:
                return
            old = selected_preset_var.get().strip()
            if not old:
                return
            new_name = simpledialog.askstring("Rename preset", "New preset name:", parent=dialog)
            if not new_name:
                return
            self.persistence.rename_preset(launcher_name, old, new_name.strip())
            selected_preset_var.set(new_name.strip())
            refresh_presets()

        def delete_preset() -> None:
            if not self.persistence:
                return
            name = selected_preset_var.get().strip()
            if not name:
                return
            self.persistence.delete_preset(launcher_name, name)
            selected_preset_var.set("")
            refresh_presets()

        ttk.Button(presets_row, text="Apply", command=on_select_preset).pack(side="left", padx=2)
        ttk.Button(presets_row, text="Save", command=lambda: save_preset(overwrite=False)).pack(side="left", padx=2)
        ttk.Button(presets_row, text="Overwrite", command=lambda: save_preset(overwrite=True)).pack(side="left", padx=2)
        ttk.Button(presets_row, text="Rename", command=rename_preset).pack(side="left", padx=2)
        ttk.Button(presets_row, text="Delete", command=delete_preset).pack(side="left", padx=2)
        preset_combo.bind("<<ComboboxSelected>>", on_select_preset)
        refresh_presets()

        def on_run() -> None:
            values, errors = collect_v2_form_values(fields)
            if errors:
                messagebox.showerror("Validation error", "\n".join(errors), parent=dialog)
                return
            if self.persistence:
                self.persistence.set_last_values(launcher_name, values)
                selected = selected_preset_var.get().strip() or None
                self.persistence.set_last_selected_preset(launcher_name, selected)
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
                state_values: dict[str, Any] | None = None
                preset_values: dict[str, Any] | None = None
                if self.persistence:
                    state_values = self.persistence.get_last_values(launcher_name)
                    selected = self.persistence.get_last_selected_preset(launcher_name)
                    if selected:
                        preset_values = self.persistence.apply_preset_values(launcher_name, selected)
                result = run_launcher(
                    self.doc,
                    launcher_name,
                    values,
                    selected_profile_name=(self.profile_var.get() or None),
                    state_values=state_values,
                    preset_values=preset_values,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML-driven CLI UI (v2)")
    parser.add_argument("config", nargs="?", default=None)
    parser.add_argument(
        "--settings",
        help="Path to INI file with [ui] default_yaml.",
        default="app.ini",
    )
    args = parser.parse_args()

    # Reuse existing settings parser for compatibility with app.ini files.
    settings = load_launch_settings(args.settings)
    default_config = settings["default_yaml"] or Path(DEFAULT_CONFIG_PATH)
    config_path = Path(args.config) if args.config else default_config

    app = AppV2(str(config_path))
    app.mainloop()


if __name__ == "__main__":
    main()
