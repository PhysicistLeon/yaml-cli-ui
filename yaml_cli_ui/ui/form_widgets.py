"""Reusable form helpers for Tk-based forms in v1/v2 UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, ttk
import yaml

from yaml_cli_ui.v2.models import ParamDef, ParamType, SecretSource


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


def _display_fixed_value(param: ParamDef, value: Any) -> str:
    if param.type == ParamType.SECRET:
        return "******"
    return str(value)


def _secret_source_display(param: ParamDef) -> str:
    if param.source == SecretSource.ENV:
        return f"<env:{param.env or 'MISSING_ENV'}>"
    if param.source == SecretSource.VAULT:
        return "<vault>"
    return ""


LONG_ENTRY_WIDTH = 60


def _should_use_slider(param: ParamDef) -> bool:
    if param.type not in (ParamType.INT, ParamType.FLOAT):
        return False
    if param.widget == "slider":
        return True
    if param.widget is not None:
        return False
    return param.min is not None and param.max is not None


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _slider_decimals(param: ParamDef, step: float) -> int:
    if param.type == ParamType.INT:
        return 0
    if param.step in (None, ""):
        return 3
    try:
        decimal = Decimal(str(param.step)).normalize()
    except (InvalidOperation, ValueError):
        return 3
    exponent = decimal.as_tuple().exponent
    return min(6, max(0, -exponent))


def _normalize_slider_value(
    raw_value: Any,
    *,
    minimum: float,
    maximum: float,
    step: float,
    decimals: int,
    ptype: ParamType,
) -> int | float:
    current = _safe_float(raw_value, minimum)
    clamped = min(maximum, max(minimum, current))
    snapped = round((clamped - minimum) / step) * step + minimum
    bounded = min(maximum, max(minimum, snapped))
    if ptype == ParamType.INT:
        return int(round(bounded))
    return round(float(bounded), decimals)


def _create_numeric_slider(parent: tk.Widget, param: ParamDef, value: Any) -> ttk.Frame:
    frame = ttk.Frame(parent)
    minimum = _safe_float(param.min, 0.0)
    maximum = _safe_float(param.max, 100.0)
    step = _safe_float(param.step, 1.0)
    if step <= 0:
        step = 1.0

    decimals = _slider_decimals(param, step)
    if param.type == ParamType.INT:
        var: tk.Variable = tk.IntVar(value=int(minimum))
    else:
        var = tk.DoubleVar(value=minimum)

    value_label = ttk.Label(frame, width=10, text="")

    def _format_number(v: float) -> str:
        return str(int(round(v))) if param.type == ParamType.INT else f"{v:.{decimals}f}".rstrip("0").rstrip(".")

    def _set_normalized(raw: Any) -> None:
        normalized = _normalize_slider_value(
            raw,
            minimum=minimum,
            maximum=maximum,
            step=step,
            decimals=decimals,
            ptype=param.type,
        )
        if param.type == ParamType.INT:
            if int(var.get()) != int(normalized):
                var.set(int(normalized))
            value_label.configure(text=str(int(normalized)))
            return
        if abs(float(var.get()) - float(normalized)) > 1e-9:
            var.set(float(normalized))
        value_label.configure(text=_format_number(float(normalized)))

    def _on_scale(raw: str) -> None:
        _set_normalized(raw)

    scale = ttk.Scale(frame, from_=minimum, to=maximum, variable=var, command=_on_scale)
    scale.pack(side="left", fill="x", expand=True)
    value_label.pack(side="left", padx=(8, 0))
    _set_normalized(value)

    frame.slider_var = var
    frame.slider_min = minimum
    frame.slider_max = maximum
    frame.slider_step = step
    frame.slider_type = param.type
    frame.slider_decimals = decimals
    frame.value_label = value_label
    frame.scale = scale
    frame.set_slider_value = _set_normalized
    return frame


def create_v2_form_fields(
    parent: tk.Widget,
    params: dict[str, ParamDef],
    *,
    initial_values: dict[str, Any] | None = None,
    fixed_values: dict[str, Any] | None = None,
) -> dict[str, FormField]:
    """Create v2 launcher form fields with an expanding value column.

    Contract:
    - editable fields are always rendered for provided `params`; prefilled values only
      initialize widgets and must not hide rows;
    - value column (index 1) expands horizontally;
    - path/string/fixed-like entries use a conservative wide default width.
    """

    initial_values = initial_values or {}
    fixed_values = fixed_values or {}
    fields: dict[str, FormField] = {}

    parent.columnconfigure(1, weight=1)

    for row, (name, param) in enumerate(params.items()):
        label = param.title or name
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)

        if name in fixed_values:
            entry = ttk.Entry(parent, width=LONG_ENTRY_WIDTH)
            entry.insert(0, _display_fixed_value(param, fixed_values[name]))
            entry.configure(state="disabled")
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            fields[name] = FormField(name, param, entry, fixed=True, fixed_value=fixed_values[name])
            continue

        value = initial_values.get(name, _default_value(param))
        fields[name] = FormField(name, param, _create_widget(parent, param, value, row=row))

    return fields


def _create_widget(parent: tk.Widget, param: ParamDef, value: Any, *, row: int) -> Any:
    ptype = param.type
    widget: Any

    if ptype == ParamType.SECRET and param.source in (SecretSource.ENV, SecretSource.VAULT):
        widget = ttk.Entry(parent, width=LONG_ENTRY_WIDTH)
        widget.insert(0, _secret_source_display(param))
        widget.configure(state="disabled")
    elif ptype in (ParamType.INT, ParamType.FLOAT) and _should_use_slider(param):
        widget = _create_numeric_slider(parent, param, value)
    elif ptype in (ParamType.STRING, ParamType.INT, ParamType.FLOAT, ParamType.SECRET):
        widget = ttk.Entry(parent, width=LONG_ENTRY_WIDTH, show="*" if ptype == ParamType.SECRET else "")
        if value not in (None, ""):
            widget.insert(0, str(value))
    elif ptype == ParamType.TEXT:
        widget = tk.Text(parent, height=4)
        if value not in (None, ""):
            widget.insert("1.0", str(value))
    elif ptype == ParamType.BOOL:
        var = tk.BooleanVar(value=bool(value))
        widget = ttk.Checkbutton(parent, variable=var)
        widget.var = var
    elif ptype == ParamType.CHOICE:
        widget = ttk.Combobox(parent, values=list(param.options or []), state="readonly")
        if value not in (None, ""):
            widget.set(str(value))
    elif ptype == ParamType.MULTICHOICE:
        widget = tk.Listbox(parent, selectmode="multiple", exportselection=False, height=5)
        options = [str(x) for x in (param.options or [])]
        for opt in options:
            widget.insert("end", opt)
        selected = set(value) if isinstance(value, list) else set()
        for idx, opt in enumerate(options):
            if opt in selected:
                widget.selection_set(idx)
    elif ptype in (ParamType.FILEPATH, ParamType.DIRPATH):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        entry = ttk.Entry(frame, width=LONG_ENTRY_WIDTH)
        if value not in (None, ""):
            entry.insert(0, str(value))
        entry.grid(row=0, column=0, sticky="ew")

        def browse() -> None:
            selected = filedialog.askdirectory() if ptype == ParamType.DIRPATH else filedialog.askopenfilename()
            if selected:
                entry.delete(0, "end")
                entry.insert(0, selected)

        ttk.Button(frame, text="Browse", command=browse).grid(row=0, column=1, padx=(6, 0), sticky="e")
        frame.entry = entry
        widget = frame
    elif ptype in (ParamType.KV_LIST, ParamType.STRUCT_LIST):
        widget = tk.Text(parent, height=5)
        if value not in (None, ""):
            widget.insert("1.0", yaml.safe_dump(value, allow_unicode=True))
    else:
        widget = ttk.Entry(parent)
        if value not in (None, ""):
            widget.insert(0, str(value))

    widget.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
    return widget


def _resolve_secret_value(param: ParamDef, raw_value: Any) -> Any:
    if param.source == SecretSource.ENV:
        if not param.env:
            return ""
        return os.environ.get(param.env, "")
    if param.source == SecretSource.VAULT:
        # Vault resolution is intentionally deferred in this step.
        return "<vault>"
    return raw_value


def collect_v2_form_values(fields: dict[str, FormField]) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    errors: list[str] = []
    for name, field in fields.items():
        try:
            raw_value = field.fixed_value if field.fixed else _read_widget_value(field.widget, field.param)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue

        value = _resolve_secret_value(field.param, raw_value) if field.param.type == ParamType.SECRET else raw_value

        if field.param.required and (value in (None, "", [])):
            errors.append(f"{name} is required")

        if field.param.type in (ParamType.FILEPATH, ParamType.DIRPATH) and value:
            path = Path(str(value))
            if field.param.must_exist:
                if not path.exists():
                    errors.append(f"{name} path does not exist")
                elif field.param.type == ParamType.FILEPATH and not path.is_file():
                    errors.append(f"{name} must be a file")
                elif field.param.type == ParamType.DIRPATH and not path.is_dir():
                    errors.append(f"{name} must be a directory")

        data[name] = value

    return data, errors


def _read_widget_value(widget: Any, param: ParamDef) -> Any:
    ptype = param.type
    value: Any

    if ptype == ParamType.TEXT:
        value = widget.get("1.0", "end").strip()
    elif ptype == ParamType.BOOL:
        value = bool(widget.var.get())
    elif ptype == ParamType.MULTICHOICE:
        value = [widget.get(i) for i in widget.curselection()]
    elif ptype in (ParamType.FILEPATH, ParamType.DIRPATH):
        value = widget.entry.get().strip()
    elif ptype in (ParamType.KV_LIST, ParamType.STRUCT_LIST):
        raw = widget.get("1.0", "end").strip()
        parsed = [] if not raw else yaml.safe_load(raw)
        if not isinstance(parsed, list):
            raise ValueError("must be a list")
        value = parsed
    elif ptype in (ParamType.INT, ParamType.FLOAT) and hasattr(widget, "slider_var"):
        value = widget.slider_var.get()
        if ptype == ParamType.INT:
            value = int(value)
        else:
            value = float(value)
    else:
        raw = widget.get().strip() if hasattr(widget, "get") else ""
        if ptype == ParamType.INT and raw != "":
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError("must be an integer") from exc
        elif ptype == ParamType.FLOAT and raw != "":
            try:
                value = float(raw)
            except ValueError as exc:
                raise ValueError("must be a float") from exc
        else:
            value = raw

    return value


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
    if param.type in (ParamType.INT, ParamType.FLOAT) and hasattr(widget, "set_slider_value"):
        widget.set_slider_value(value if value != "" else widget.slider_min)
        return
    if hasattr(widget, "delete"):
        widget.delete(0, "end")
    if value != "" and hasattr(widget, "insert"):
        widget.insert(0, str(value))
