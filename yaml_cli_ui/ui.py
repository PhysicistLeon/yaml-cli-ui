from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .engine import WorkflowEngine, load_workflow, parse_structured_field


class AppUI:
    def __init__(self, root: tk.Tk, yaml_path: str):
        self.root = root
        self.yaml_path = Path(yaml_path)
        self.doc = load_workflow(self.yaml_path)
        self.engine = WorkflowEngine(self.doc)
        self.field_vars: dict[str, Any] = {}
        self.current_action = tk.StringVar()
        self.log_widget = None

        self.root.title(self.doc.get("app", {}).get("title", "YAML CLI UI"))
        self._build_shell()
        self.reload_yaml()

    def _build_shell(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="YAML file").pack(side="left")
        self.path_var = tk.StringVar(value=str(self.yaml_path))
        ttk.Entry(top, textvariable=self.path_var, width=60).pack(side="left", padx=6)
        ttk.Button(top, text="Browse", command=self._browse_yaml).pack(side="left")
        ttk.Button(top, text="Reload", command=self.reload_yaml).pack(side="left", padx=4)

        self.action_frame = ttk.LabelFrame(self.root, text="Action")
        self.action_frame.pack(fill="x", padx=10, pady=6)
        self.form_frame = ttk.LabelFrame(self.root, text="Form")
        self.form_frame.pack(fill="x", padx=10, pady=6)

        run_bar = ttk.Frame(self.root)
        run_bar.pack(fill="x", padx=10, pady=4)
        ttk.Button(run_bar, text="Run", command=self.run_current_action).pack(side="left")
        ttk.Button(run_bar, text="Open workdir", command=self.open_workdir).pack(side="left", padx=6)

        logs = ttk.LabelFrame(self.root, text="Logs")
        logs.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_widget = tk.Text(logs, height=16)
        self.log_widget.pack(fill="both", expand=True)

    def _browse_yaml(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("YAML", "*.yml *.yaml")])
        if path:
            self.path_var.set(path)
            self.yaml_path = Path(path)

    def reload_yaml(self) -> None:
        self.yaml_path = Path(self.path_var.get())
        self.doc = load_workflow(self.yaml_path)
        self.engine = WorkflowEngine(self.doc)
        for child in self.action_frame.winfo_children():
            child.destroy()
        for child in self.form_frame.winfo_children():
            child.destroy()

        actions = list(self.doc["actions"].keys())
        if not actions:
            raise ValueError("No actions found")
        self.current_action.set(actions[0])
        ttk.Combobox(
            self.action_frame,
            values=actions,
            state="readonly",
            textvariable=self.current_action,
        ).pack(fill="x", padx=8, pady=8)
        self.current_action.trace_add("write", lambda *_: self.render_form())
        self.render_form()
        self.log("YAML reloaded")

    def render_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_vars = {}
        action = self.doc["actions"][self.current_action.get()]
        row = 0
        for field in action.get("form", {}).get("fields", []):
            fid = field["id"]
            ftype = field["type"]
            ttk.Label(self.form_frame, text=field.get("label", fid)).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            default = field.get("default", "")

            if ftype in {"string", "path", "int", "float", "secret"}:
                v = tk.StringVar(value="" if default is None else str(default))
                show = "*" if ftype == "secret" and field.get("source", "inline") == "inline" else ""
                ttk.Entry(self.form_frame, textvariable=v, show=show, width=70).grid(row=row, column=1, sticky="ew", padx=6)
                self.field_vars[fid] = (field, v)
            elif ftype == "text":
                t = tk.Text(self.form_frame, height=4, width=70)
                if default:
                    t.insert("1.0", str(default))
                t.grid(row=row, column=1, sticky="ew", padx=6)
                self.field_vars[fid] = (field, t)
            elif ftype == "bool":
                v = tk.BooleanVar(value=bool(default))
                ttk.Checkbutton(self.form_frame, variable=v).grid(row=row, column=1, sticky="w")
                self.field_vars[fid] = (field, v)
            elif ftype == "tri_bool":
                v = tk.StringVar(value=str(default or "auto"))
                ttk.Combobox(self.form_frame, textvariable=v, values=["auto", "true", "false"], state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=6
                )
                self.field_vars[fid] = (field, v)
            elif ftype == "choice":
                v = tk.StringVar(value=str(default or ""))
                ttk.Combobox(self.form_frame, textvariable=v, values=field.get("options", []), state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=6
                )
                self.field_vars[fid] = (field, v)
            elif ftype in {"multichoice", "kv_list", "struct_list"}:
                t = tk.Text(self.form_frame, height=4, width=70)
                if default not in (None, ""):
                    t.insert("1.0", json.dumps(default, ensure_ascii=False))
                t.grid(row=row, column=1, sticky="ew", padx=6)
                self.field_vars[fid] = (field, t)
            else:
                raise ValueError(f"Unsupported field type in UI: {ftype}")
            row += 1
        self.form_frame.columnconfigure(1, weight=1)

    def collect_form_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for fid, (field, control) in self.field_vars.items():
            ftype = field["type"]
            if isinstance(control, tk.Text):
                raw = control.get("1.0", "end").strip()
            else:
                raw = control.get()

            if ftype == "secret" and field.get("source") == "env":
                env_name = field.get("env")
                raw = os.environ.get(env_name, "") if env_name else ""
            elif ftype == "int":
                raw = int(raw) if raw != "" else None
            elif ftype == "float":
                raw = float(raw) if raw != "" else None
            elif ftype == "path" and field.get("multiple"):
                raw = parse_structured_field(raw, "path")
            elif ftype in {"kv_list", "struct_list", "multichoice"}:
                raw = parse_structured_field(raw, ftype)

            if field.get("required") and raw in (None, "", []):
                raise ValueError(f"Field '{fid}' is required")
            if ftype == "path" and field.get("must_exist"):
                if field.get("multiple"):
                    missing = [p for p in raw if not Path(p).exists()]
                    if missing:
                        raise ValueError(f"Missing paths in {fid}: {missing}")
                else:
                    if raw and not Path(str(raw)).exists():
                        raise ValueError(f"Path for '{fid}' does not exist: {raw}")
            if ftype == "choice" and raw and raw not in field.get("options", []):
                raise ValueError(f"Invalid choice for {fid}")
            data[fid] = raw
        return data

    def log(self, text: str) -> None:
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")

    def run_current_action(self) -> None:
        def _run() -> None:
            try:
                form_data = self.collect_form_data()
                self.log(f"Running action: {self.current_action.get()}")
                results = self.engine.run_action(self.current_action.get(), form_data)
                self.log(json.dumps(results, ensure_ascii=False, indent=2))
            except Exception as exc:  # noqa: BLE001
                self.log(f"ERROR: {exc}")
                messagebox.showerror("Run failed", str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def open_workdir(self) -> None:
        workdir = self.doc.get("app", {}).get("workdir", str(Path.cwd()))
        path = Path(workdir)
        if os.name == "nt":
            os.system(f'explorer.exe "{path}"')
        else:
            self.log(f"Open folder on this OS manually: {path}")


def run_ui(yaml_path: str) -> None:
    root = tk.Tk()
    AppUI(root, yaml_path)
    root.mainloop()
