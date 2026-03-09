"""Reusable form widgets for legacy App and AppV2."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

import yaml

from yaml_cli_ui.v2.models import ParamDef, ParamType, SecretSource


class FormValidationError(ValueError):
    """Raised when form data is invalid."""


class ParamForm:
    def __init__(
        self,
        parent: tk.Widget,
        *,
        params: dict[str, ParamDef],
        initial_values: dict[str, Any] | None = None,
        fixed_values: dict[str, Any] | None = None,
        browse_dir: Path | None = None,
    ):
        self.parent = parent
        self.params = params
        self.initial_values = initial_values or {}
        self.fixed_values = fixed_values or {}
        self.browse_dir = browse_dir
        self.fields: dict[str, tuple[ParamDef, Any]] = {}
        self.fixed_labels: dict[str, ttk.Entry] = {}
        self._build()

    def _build(self) -> None:
        row = 0
        for name, param in self.params.items():
            if name in self.fixed_values:
                ttk.Label(self.parent, text=param.title or name).grid(row=row, column=0, sticky="w", padx=5, pady=4)
                entry = ttk.Entry(self.parent, state="readonly")
                entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
                entry.configure(state="normal")
                entry.insert(0, _display_fixed_value(param, self.fixed_values[name]))
                entry.configure(state="readonly")
                self.fixed_labels[name] = entry
                row += 1
                continue

            ttk.Label(self.parent, text=param.title or name).grid(row=row, column=0, sticky="w", padx=5, pady=4)
            widget = self._make_widget(row, name, param)
            self.fields[name] = (param, widget)
            self._set_widget_value(param, widget, self.initial_values.get(name, param.default))
            row += 1
        self.parent.columnconfigure(1, weight=1)

    def _make_widget(self, row: int, name: str, param: ParamDef) -> Any:
        ptype = param.type.value
        if ptype == ParamType.TEXT.value:
            w = tk.Text(self.parent, height=4)
            w.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            return w
        if ptype == ParamType.BOOL.value:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self.parent, variable=var)
            cb.var = var
            cb.grid(row=row, column=1, sticky="w", padx=5, pady=4)
            return cb
        if ptype in {ParamType.CHOICE.value, ParamType.MULTICHOICE.value}:
            options = [str(v) for v in (param.options or [])]
            if ptype == ParamType.CHOICE.value:
                cb = ttk.Combobox(self.parent, values=options, state="readonly")
                cb.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
                return cb
            lb = tk.Listbox(self.parent, selectmode="extended", exportselection=False, height=min(6, max(3, len(options) or 3)))
            for option in options:
                lb.insert("end", option)
            lb.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            return lb
        if ptype in {ParamType.FILEPATH.value, ParamType.DIRPATH.value}:
            frame = ttk.Frame(self.parent)
            frame.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            frame.columnconfigure(0, weight=1)
            entry = ttk.Entry(frame)
            entry.grid(row=0, column=0, sticky="ew")
            ttk.Button(frame, text="Browse", command=lambda: self._pick_path(entry, ptype)).grid(row=0, column=1, padx=(6, 0))
            return entry
        show = "*" if ptype == ParamType.SECRET.value else None
        entry = ttk.Entry(self.parent, show=show)
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
        return entry

    def _pick_path(self, entry: ttk.Entry, ptype: str) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.browse_dir)) if ptype == ParamType.DIRPATH.value else filedialog.askopenfilename(initialdir=str(self.browse_dir) if self.browse_dir else None)
        if selected:
            entry.delete(0, "end")
            entry.insert(0, selected)

    def _set_widget_value(self, param: ParamDef, widget: Any, value: Any) -> None:
        if value is None:
            value = ""
        ptype = param.type.value
        if ptype == ParamType.TEXT.value:
            widget.delete("1.0", "end")
            if value != "":
                widget.insert("1.0", str(value))
            return
        if ptype == ParamType.BOOL.value:
            widget.var.set(bool(value))
            return
        if ptype == ParamType.CHOICE.value:
            widget.set(str(value))
            return
        if ptype == ParamType.MULTICHOICE.value:
            widget.selection_clear(0, "end")
            selected = set(value if isinstance(value, list) else [])
            for idx in range(widget.size()):
                if widget.get(idx) in selected:
                    widget.selection_set(idx)
            return
        widget.delete(0, "end")
        if value != "":
            widget.insert(0, str(value))

    def has_editable_fields(self) -> bool:
        return bool(self.fields)

    def collect(self) -> dict[str, Any]:
        data = dict(self.fixed_values)
        errors: list[str] = []
        for name, (param, widget) in self.fields.items():
            value = self._widget_value(param, widget)
            if param.required and (value == "" or value is None):
                errors.append(f"{name} is required")
            if param.type.value == ParamType.FILEPATH.value and param.must_exist and value and not Path(value).is_file():
                errors.append(f"{name} must be an existing file")
            if param.type.value == ParamType.DIRPATH.value and param.must_exist and value and not Path(value).is_dir():
                errors.append(f"{name} must be an existing directory")
            data[name] = value
        if errors:
            raise FormValidationError("\n".join(errors))
        return data

    def _widget_value(self, param: ParamDef, widget: Any) -> Any:
        ptype = param.type.value
        if ptype == ParamType.TEXT.value:
            raw = widget.get("1.0", "end").strip()
            return raw
        if ptype == ParamType.BOOL.value:
            return bool(widget.var.get())
        raw = widget.get().strip() if hasattr(widget, "get") else ""
        if ptype == ParamType.INT.value:
            return int(raw) if raw else None
        if ptype == ParamType.FLOAT.value:
            return float(raw) if raw else None
        if ptype == ParamType.MULTICHOICE.value:
            return [widget.get(i) for i in widget.curselection()]
        if ptype in {ParamType.KV_LIST.value, ParamType.STRUCT_LIST.value}:
            loaded = [] if not raw else yaml.safe_load(raw)
            if not isinstance(loaded, list):
                raise FormValidationError(f"{ptype} for parameter must be a YAML list")
            return loaded
        if ptype == ParamType.SECRET.value and param.source == SecretSource.ENV and param.env:
            return os.environ.get(param.env, "")
        return raw


def _display_fixed_value(param: ParamDef, value: Any) -> str:
    if param.type == ParamType.SECRET:
        if param.source == SecretSource.ENV and param.env:
            return f"<env:{param.env}>"
        if param.source == SecretSource.VAULT:
            return "<vault>"
        return "******"
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
