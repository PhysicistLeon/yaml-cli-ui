from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .engine import ValidationError, WorkflowEngine


class App(tk.Tk):
    def __init__(self, engine: WorkflowEngine, yaml_path: str):
        super().__init__()
        self.engine = engine
        self.yaml_path = yaml_path
        self.title(engine.config.get("app", {}).get("title", "YAML CLI UI"))
        self.geometry("900x700")

        self.action_var = tk.StringVar(value=self.engine.action_ids()[0])
        self.widgets: dict[str, Any] = {}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="Action:").pack(side="left")
        ttk.Combobox(top, textvariable=self.action_var, values=self.engine.action_ids(), state="readonly").pack(side="left", padx=6)
        ttk.Button(top, text="Reload YAML", command=self.reload_yaml).pack(side="left", padx=6)
        ttk.Button(top, text="Run", command=self.run_action).pack(side="left", padx=6)

        self.form_frame = ttk.Frame(self)
        self.form_frame.pack(fill="x", padx=8, pady=8)

        self.output = tk.Text(self, wrap="word", height=25)
        self.output.pack(fill="both", expand=True, padx=8, pady=8)

        self.action_var.trace_add("write", lambda *_: self.render_form())
        self.render_form()

    def reload_yaml(self) -> None:
        try:
            self.engine = WorkflowEngine.from_file(self.yaml_path)
            self.action_var.set(self.engine.action_ids()[0])
            self.output.insert("end", "\n[info] YAML reloaded\n")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Reload failed", str(exc))

    def render_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.widgets.clear()
        action = self.engine.get_action(self.action_var.get())
        fields = ((action.get("form") or {}).get("fields") or [])

        for row, field in enumerate(fields):
            field_id = field["id"]
            ftype = field["type"]
            ttk.Label(self.form_frame, text=field.get("label", field_id)).grid(row=row, column=0, sticky="w", pady=4)
            widget = self._build_widget(self.form_frame, field)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self.widgets[field_id] = (field, widget)
        self.form_frame.columnconfigure(1, weight=1)

    def _build_widget(self, parent: ttk.Frame, field: dict[str, Any]) -> tk.Widget:
        ftype = field["type"]
        default = field.get("default", "")
        if ftype in {"string", "path", "secret", "int", "float"}:
            var = tk.StringVar(value=str(default))
            entry = ttk.Entry(parent, textvariable=var, show="*" if ftype == "secret" and field.get("source") != "env" else "")
            entry.var = var  # type: ignore[attr-defined]
            return entry
        if ftype == "text":
            txt = tk.Text(parent, height=4)
            if default:
                txt.insert("1.0", str(default))
            return txt
        if ftype == "bool":
            var = tk.BooleanVar(value=bool(default))
            chk = ttk.Checkbutton(parent, variable=var)
            chk.var = var  # type: ignore[attr-defined]
            return chk
        if ftype == "tri_bool":
            var = tk.StringVar(value=str(default or "auto"))
            combo = ttk.Combobox(parent, textvariable=var, values=["auto", "true", "false"], state="readonly")
            combo.var = var  # type: ignore[attr-defined]
            return combo
        if ftype in {"choice", "multichoice"}:
            var = tk.StringVar(value=str(default))
            combo = ttk.Combobox(parent, textvariable=var, values=field.get("options", []))
            combo.var = var  # type: ignore[attr-defined]
            return combo
        if ftype in {"kv_list", "struct_list"}:
            txt = tk.Text(parent, height=5)
            txt.insert("1.0", json.dumps(default if default else [], ensure_ascii=False))
            return txt
        return ttk.Entry(parent)

    def _extract_value(self, field: dict[str, Any], widget: tk.Widget) -> Any:
        ftype = field["type"]
        if isinstance(widget, tk.Text):
            raw = widget.get("1.0", "end").strip()
            if ftype in {"kv_list", "struct_list"}:
                return json.loads(raw or "[]")
            return raw
        var = getattr(widget, "var", None)
        value = var.get() if var else ""
        if ftype == "int":
            return int(value) if str(value).strip() else None
        if ftype == "float":
            return float(value) if str(value).strip() else None
        if ftype == "multichoice":
            if isinstance(value, str):
                return [v.strip() for v in value.split(",") if v.strip()]
        if ftype == "secret" and field.get("source") == "env":
            return None
        return value

    def collect_form_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field_id, (field, widget) in self.widgets.items():
            value = self._extract_value(field, widget)
            if field.get("required") and (value is None or value == "" or value == []):
                raise ValidationError(f"Field {field_id} is required")
            if field["type"] == "path" and field.get("must_exist") and value:
                import os

                if field.get("multiple"):
                    missing = [p for p in str(value).split(",") if p and not os.path.exists(p)]
                    if missing:
                        raise ValidationError(f"Path(s) do not exist: {missing}")
                elif not os.path.exists(str(value)):
                    raise ValidationError(f"Path does not exist: {value}")
            out[field_id] = value
        return out

    def run_action(self) -> None:
        self.output.delete("1.0", "end")
        try:
            data = self.collect_form_data()
            commands, results = self.engine.run_action(self.action_var.get(), data)
            self.output.insert("end", "Commands:\n")
            for sid, cmd in commands:
                self.output.insert("end", f"[{sid}] {cmd}\n")
            self.output.insert("end", "\nResults:\n")
            for sid, result in results.items():
                self.output.insert("end", f"[{sid}] exit={result.exit_code} duration={result.duration_ms}ms\n")
                if result.stdout:
                    self.output.insert("end", f"stdout:\n{result.stdout}\n")
                if result.stderr:
                    self.output.insert("end", f"stderr:\n{result.stderr}\n")
        except Exception as exc:  # noqa: BLE001
            self.output.insert("end", f"ERROR: {exc}\n")
            messagebox.showerror("Execution failed", str(exc))
