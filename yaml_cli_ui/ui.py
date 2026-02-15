from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

from .engine import EngineError, PipelineEngine, validate_config


class App(tk.Tk):
    def __init__(self, config_path: Path):
        super().__init__()
        self.config_path = config_path
        self.title("YAML CLI UI")
        self.geometry("960x700")

        self.config_data: dict[str, Any] = {}
        self.engine: PipelineEngine | None = None
        self.form_widgets: dict[str, Any] = {}
        self.form_defs: list[dict[str, Any]] = []
        self.action_var = tk.StringVar()

        self._build_layout()
        self.reload_config()

    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Label(top, text="YAML file").pack(side="left")
        self.path_var = tk.StringVar(value=str(self.config_path))
        ttk.Entry(top, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Browse", command=self.choose_file).pack(side="left")
        ttk.Button(top, text="Reload", command=self.reload_config).pack(side="left", padx=4)

        action_row = ttk.Frame(self)
        action_row.pack(fill="x", padx=8)
        ttk.Label(action_row, text="Action").pack(side="left")
        self.action_combo = ttk.Combobox(action_row, textvariable=self.action_var, state="readonly")
        self.action_combo.pack(side="left", fill="x", expand=True, padx=6)
        self.action_combo.bind("<<ComboboxSelected>>", lambda _: self.render_form())

        body = ttk.Panedwindow(self, orient=tk.VERTICAL)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self.form_frame = ttk.Frame(body)
        body.add(self.form_frame, weight=3)

        bottom = ttk.Frame(body)
        body.add(bottom, weight=2)

        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
        ttk.Button(btns, text="Run", command=self.run_action).pack(side="left")

        self.log = tk.Text(bottom, wrap="word")
        self.log.pack(fill="both", expand=True, pady=6)

    def choose_file(self) -> None:
        file_path = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml")])
        if file_path:
            self.path_var.set(file_path)
            self.reload_config()

    def reload_config(self) -> None:
        try:
            path = Path(self.path_var.get())
            with path.open("r", encoding="utf-8") as f:
                self.config_data = yaml.safe_load(f) or {}
            validate_config(self.config_data)
            self.engine = PipelineEngine(self.config_data)
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))
            return

        self.config_path = Path(self.path_var.get())
        actions = list(self.config_data.get("actions", {}).keys())
        self.action_combo["values"] = actions
        if actions:
            self.action_var.set(actions[0])
        self.title(self.config_data.get("app", {}).get("title", "YAML CLI UI"))
        self.render_form()

    def render_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.form_widgets.clear()

        action = self.config_data.get("actions", {}).get(self.action_var.get(), {})
        fields = action.get("form", {}).get("fields", [])
        self.form_defs = fields

        for idx, field in enumerate(fields):
            fid = field["id"]
            ftype = field.get("type", "string")
            label = field.get("label", fid)
            ttk.Label(self.form_frame, text=label).grid(row=idx, column=0, sticky="w", padx=4, pady=4)

            default = field.get("default")
            widget: Any
            if ftype in ("string", "path", "secret", "int", "float"):
                var = tk.StringVar(value="" if default is None else str(default))
                show = "*" if ftype == "secret" and field.get("source", "inline") == "inline" else ""
                widget = ttk.Entry(self.form_frame, textvariable=var, show=show)
                widget.var = var
                widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
            elif ftype == "text":
                widget = tk.Text(self.form_frame, height=4)
                if default:
                    widget.insert("1.0", str(default))
                widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
            elif ftype == "bool":
                var = tk.BooleanVar(value=bool(default))
                widget = ttk.Checkbutton(self.form_frame, variable=var)
                widget.var = var
                widget.grid(row=idx, column=1, sticky="w")
            elif ftype == "tri_bool":
                var = tk.StringVar(value=str(default or "auto"))
                widget = ttk.Combobox(self.form_frame, textvariable=var, state="readonly", values=["auto", "true", "false"])
                widget.var = var
                widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
            elif ftype in ("choice", "multichoice"):
                options = field.get("options", [])
                if ftype == "choice":
                    var = tk.StringVar(value=str(default or (options[0] if options else "")))
                    widget = ttk.Combobox(self.form_frame, textvariable=var, state="readonly", values=options)
                    widget.var = var
                    widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
                else:
                    widget = tk.Listbox(self.form_frame, selectmode="multiple", height=min(5, max(1, len(options))))
                    for opt in options:
                        widget.insert(tk.END, opt)
                    widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
            elif ftype in ("kv_list", "struct_list"):
                widget = tk.Text(self.form_frame, height=5)
                if default:
                    widget.insert("1.0", json.dumps(default, ensure_ascii=False, indent=2))
                widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)
            else:
                var = tk.StringVar(value="" if default is None else str(default))
                widget = ttk.Entry(self.form_frame, textvariable=var)
                widget.var = var
                widget.grid(row=idx, column=1, sticky="ew", padx=4, pady=4)

            self.form_widgets[fid] = (field, widget)

        self.form_frame.columnconfigure(1, weight=1)

    def collect_form(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for fid, (field, widget) in self.form_widgets.items():
            ftype = field.get("type", "string")
            if isinstance(widget, tk.Text):
                raw = widget.get("1.0", "end").strip()
            elif isinstance(widget, tk.Listbox):
                raw = [widget.get(i) for i in widget.curselection()]
            elif hasattr(widget, "var"):
                raw = widget.var.get()
            else:
                raw = ""

            if ftype == "int" and raw != "":
                raw = int(raw)
            elif ftype == "float" and raw != "":
                raw = float(raw)
            elif ftype in ("kv_list", "struct_list"):
                raw = [] if raw == "" else json.loads(raw)
            elif ftype == "secret" and field.get("source") == "env":
                raw = "${env." + field["env"] + "}"

            if field.get("required") and raw in (None, "", []):
                raise EngineError(f"Field '{fid}' is required")
            if ftype == "path" and raw:
                p = Path(raw)
                if field.get("must_exist") and not p.exists():
                    raise EngineError(f"Path for '{fid}' does not exist: {raw}")

            data[fid] = raw
        return data

    def run_action(self) -> None:
        if self.engine is None:
            return
        try:
            action_id = self.action_var.get()
            form_data = self.collect_form()
            results = self.engine.run_action(action_id, form_data)
            self.log.delete("1.0", "end")
            for step_id, result in results.items():
                self.log.insert("end", f"[{step_id}] exit={result.exit_code} duration={result.duration_ms}ms\n")
                if result.stdout:
                    self.log.insert("end", f"stdout:\n{result.stdout}\n")
                if result.stderr:
                    self.log.insert("end", f"stderr:\n{result.stderr}\n")
                self.log.insert("end", "\n")
        except Exception as exc:
            messagebox.showerror("Execution error", str(exc))


def launch(path: str) -> None:
    app = App(Path(path))
    app.mainloop()
