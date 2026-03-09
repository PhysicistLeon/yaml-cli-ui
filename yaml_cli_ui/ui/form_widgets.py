"""Reusable form helpers for Tk-based forms in v1/v2 UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, ttk
import yaml

from yaml_cli_ui.v2.models import ParamDef, ParamType


@dataclass
class FormField:
    name: str
    param: ParamDef
    widget: Any
    fixed: bool = False
    fixed_value: Any | None = None


def _default_value(param: ParamDef) -> Any:
    if param.default is not None:
        return param.default
    if param.type == ParamType.BOOL:
        return False
    if param.type == ParamType.MULTICHOICE:
        return []
    return ""


def create_v2_form_fields(
    parent: tk.Widget,
    params: dict[str, ParamDef],
    *,
    initial_values: dict[str, Any] | None = None,
    fixed_values: dict[str, Any] | None = None,
) -> dict[str, FormField]:
    initial_values = initial_values or {}
    fixed_values = fixed_values or {}
    fields: dict[str, FormField] = {}

    for row, (name, param) in enumerate(params.items()):
        label = param.title or name
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)

        if name in fixed_values:
            value = fixed_values[name]
            shown = "***" if param.type == ParamType.SECRET else str(value)
            entry = ttk.Entry(parent)
            entry.insert(0, shown)
            entry.configure(state="disabled")
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            fields[name] = FormField(name, param, entry, fixed=True, fixed_value=value)
            continue

        value = initial_values.get(name, _default_value(param))
        widget = _create_widget(parent, param, value)
        fields[name] = FormField(name, param, widget)

    parent.columnconfigure(1, weight=1)
    return fields


def _create_widget(parent: tk.Widget, param: ParamDef, value: Any) -> Any:
    ptype = param.type
    if ptype in (ParamType.STRING, ParamType.INT, ParamType.FLOAT, ParamType.SECRET):
        entry = ttk.Entry(parent, show="*" if ptype == ParamType.SECRET else "")
        if value not in (None, ""):
            entry.insert(0, str(value))
        entry.grid(sticky="ew", padx=5, pady=4)
        return entry
    if ptype == ParamType.TEXT:
        text = tk.Text(parent, height=4)
        if value not in (None, ""):
            text.insert("1.0", str(value))
        text.grid(sticky="ew", padx=5, pady=4)
        return text
    if ptype == ParamType.BOOL:
        var = tk.BooleanVar(value=bool(value))
        check = ttk.Checkbutton(parent, variable=var)
        check.var = var
        check.grid(sticky="w", padx=5, pady=4)
        return check
    if ptype == ParamType.CHOICE:
        combo = ttk.Combobox(parent, values=list(param.options or []), state="readonly")
        if value not in (None, ""):
            combo.set(str(value))
        combo.grid(sticky="ew", padx=5, pady=4)
        return combo
    if ptype == ParamType.MULTICHOICE:
        listbox = tk.Listbox(parent, selectmode="multiple", exportselection=False, height=5)
        options = [str(x) for x in (param.options or [])]
        for opt in options:
            listbox.insert("end", opt)
        selected = set(value) if isinstance(value, list) else set()
        for idx, opt in enumerate(options):
            if opt in selected:
                listbox.selection_set(idx)
        listbox.grid(sticky="ew", padx=5, pady=4)
        return listbox
    if ptype in (ParamType.FILEPATH, ParamType.DIRPATH):
        frame = ttk.Frame(parent)
        entry = ttk.Entry(frame)
        if value not in (None, ""):
            entry.insert(0, str(value))
        entry.pack(side="left", fill="x", expand=True)

        def browse() -> None:
            if ptype == ParamType.DIRPATH:
                selected = filedialog.askdirectory()
            else:
                selected = filedialog.askopenfilename()
            if selected:
                entry.delete(0, "end")
                entry.insert(0, selected)

        ttk.Button(frame, text="Browse", command=browse).pack(side="left", padx=(6, 0))
        frame.grid(sticky="ew", padx=5, pady=4)
        frame.entry = entry
        return frame
    if ptype in (ParamType.KV_LIST, ParamType.STRUCT_LIST):
        text = tk.Text(parent, height=5)
        if value not in (None, ""):
            text.insert("1.0", yaml.safe_dump(value, allow_unicode=True))
        text.grid(sticky="ew", padx=5, pady=4)
        return text

    entry = ttk.Entry(parent)
    if value not in (None, ""):
        entry.insert(0, str(value))
    entry.grid(sticky="ew", padx=5, pady=4)
    return entry


def collect_v2_form_values(fields: dict[str, FormField]) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    errors: list[str] = []
    for name, field in fields.items():
        if field.fixed:
            value = field.fixed_value
        else:
            value = _read_widget_value(field.widget, field.param)

        if field.param.required and (value in (None, "", [])):
            errors.append(f"{name} is required")

        if field.param.type in (ParamType.FILEPATH, ParamType.DIRPATH) and value:
            path = Path(str(value))
            if field.param.must_exist and not path.exists():
                errors.append(f"{name} path does not exist")
            if field.param.type == ParamType.FILEPATH and path.exists() and not path.is_file():
                errors.append(f"{name} must be a file")
            if field.param.type == ParamType.DIRPATH and path.exists() and not path.is_dir():
                errors.append(f"{name} must be a directory")

        if field.param.type == ParamType.SECRET and field.param.source is not None:
            env_name = field.param.env
            if env_name:
                value = os.environ.get(env_name, "")

        data[name] = value

    return data, errors


def _read_widget_value(widget: Any, param: ParamDef) -> Any:
    ptype = param.type
    if ptype == ParamType.TEXT:
        return widget.get("1.0", "end").strip()
    if ptype == ParamType.BOOL:
        return bool(widget.var.get())
    if ptype == ParamType.MULTICHOICE:
        return [widget.get(i) for i in widget.curselection()]
    if ptype in (ParamType.FILEPATH, ParamType.DIRPATH):
        return widget.entry.get().strip()
    if ptype in (ParamType.KV_LIST, ParamType.STRUCT_LIST):
        raw = widget.get("1.0", "end").strip()
        return [] if not raw else yaml.safe_load(raw)

    raw = widget.get().strip() if hasattr(widget, "get") else ""
    if ptype == ParamType.INT and raw != "":
        return int(raw)
    if ptype == ParamType.FLOAT and raw != "":
        return float(raw)
    return raw


def apply_values_to_v2_form(fields: dict[str, FormField], values: dict[str, Any]) -> None:
    for name, field in fields.items():
        target = values.get(name, _default_value(field.param))
        if field.fixed:
            continue
        _set_widget_value(field.widget, field.param, target)


def _set_widget_value(widget: Any, param: ParamDef, value: Any) -> None:
    if value is None:
        value = ""
    if param.type == ParamType.TEXT:
        widget.delete("1.0", "end")
        if value != "":
            widget.insert("1.0", str(value))
        return
    if param.type == ParamType.BOOL:
        widget.var.set(bool(value))
        return
    if param.type == ParamType.MULTICHOICE:
        widget.selection_clear(0, "end")
        selected = set(value) if isinstance(value, list) else set()
        for idx in range(widget.size()):
            if widget.get(idx) in selected:
                widget.selection_set(idx)
        return
    if param.type in (ParamType.FILEPATH, ParamType.DIRPATH):
        widget.entry.delete(0, "end")
        if value != "":
            widget.entry.insert(0, str(value))
        return
    if hasattr(widget, "delete"):
        widget.delete(0, "end")
    if value != "" and hasattr(widget, "insert"):
        widget.insert(0, str(value))
