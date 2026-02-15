from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

from .engine import EngineError, PipelineEngine, validate_config


class App(tk.Tk):
    def __init__(self, config_path: str):
        super().__init__()
        self.title("YAML CLI UI")
        self.geometry("980x700")
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.engine: PipelineEngine | None = None

        self.action_var = tk.StringVar()
        self.fields: dict[str, tuple[dict[str, Any], Any]] = {}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="YAML file:").pack(side="left")
        self.path_entry = ttk.Entry(top)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.insert(0, str(self.config_path))
        ttk.Button(top, text="Browse", command=self._browse).pack(side="left", padx=4)
        ttk.Button(top, text="Reload", command=self.load_config).pack(side="left")

        action_row = ttk.Frame(self)
        action_row.pack(fill="x", padx=10)
        ttk.Label(action_row, text="Action:").pack(side="left")
        self.action_combo = ttk.Combobox(action_row, state="readonly", textvariable=self.action_var)
        self.action_combo.pack(side="left", fill="x", expand=True, padx=6)
        self.action_combo.bind("<<ComboboxSelected>>", lambda _e: self.build_form())
        ttk.Button(action_row, text="Run", command=self.run_action).pack(side="left")

        self.form_frame = ttk.Frame(self)
        self.form_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(self, text="Output:").pack(anchor="w", padx=10)
        self.output = tk.Text(self, height=14)
        self.output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.load_config()

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml")])
        if selected:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, selected)
            self.load_config()

    def log(self, msg: str) -> None:
        self.output.insert("end", msg + "\n")
        self.output.see("end")
        self.update_idletasks()

    def load_config(self) -> None:
        try:
            self.config_path = Path(self.path_entry.get())
            self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
            validate_config(self.config)
            self.engine = PipelineEngine(self.config)
            title = self.config.get("app", {}).get("title", "YAML CLI UI")
            self.title(title)
            actions = self.config.get("actions", {})
            self.action_combo["values"] = list(actions.keys())
            if actions:
                first = list(actions.keys())[0]
                self.action_var.set(first)
            self.build_form()
            self.log(f"Loaded: {self.config_path}")
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))

    def build_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.fields.clear()

        action = self.config.get("actions", {}).get(self.action_var.get(), {})
        form = action.get("form", {})
        for i, field in enumerate(form.get("fields", [])):
            fid = field["id"]
            label = field.get("label", fid)
            ftype = field.get("type", "string")
            ttk.Label(self.form_frame, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=4)

            widget: Any
            if ftype in {"string", "path", "int", "float", "secret"}:
                show = "*" if ftype == "secret" and field.get("source", "inline") == "inline" else ""
                widget = ttk.Entry(self.form_frame, show=show)
                if "default" in field:
                    widget.insert(0, str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "text":
                widget = tk.Text(self.form_frame, height=4)
                if "default" in field:
                    widget.insert("1.0", str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "bool":
                var = tk.BooleanVar(value=bool(field.get("default", False)))
                widget = ttk.Checkbutton(self.form_frame, variable=var)
                widget.var = var
                widget.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            elif ftype == "tri_bool":
                widget = ttk.Combobox(self.form_frame, state="readonly", values=["auto", "true", "false"])
                widget.set(field.get("default", "auto"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "choice":
                widget = ttk.Combobox(self.form_frame, state="readonly", values=field.get("options", []))
                if field.get("default") is not None:
                    widget.set(field.get("default"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "multichoice":
                widget = tk.Listbox(self.form_frame, selectmode="multiple", height=5, exportselection=False)
                for opt in field.get("options", []):
                    widget.insert("end", opt)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype in {"kv_list", "struct_list"}:
                widget = tk.Text(self.form_frame, height=5)
                if "default" in field:
                    widget.insert("1.0", json.dumps(field["default"], ensure_ascii=False, indent=2))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                ttk.Label(self.form_frame, text="JSON/YAML list input").grid(row=i, column=2, sticky="w")
            else:
                widget = ttk.Entry(self.form_frame)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            self.fields[fid] = (field, widget)

        self.form_frame.columnconfigure(1, weight=1)

    def collect_form(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        errors: list[str] = []
        for fid, (field, widget) in self.fields.items():
            ftype = field.get("type", "string")
            value: Any = None
            if ftype == "text":
                value = widget.get("1.0", "end").rstrip("\n")
            elif ftype == "bool":
                value = bool(widget.var.get())
            elif ftype == "tri_bool":
                value = widget.get() or "auto"
            elif ftype == "multichoice":
                value = [widget.get(i) for i in widget.curselection()]
            elif ftype in {"kv_list", "struct_list"}:
                raw = widget.get("1.0", "end").strip()
                value = [] if not raw else yaml.safe_load(raw)
                if not isinstance(value, list):
                    errors.append(f"{fid} must be a list")
            else:
                value = widget.get().strip()
                if ftype == "int" and value != "":
                    value = int(value)
                if ftype == "float" and value != "":
                    value = float(value)
                if ftype == "secret" and field.get("source") == "env":
                    value = None

            if field.get("required") and (value is None or value == "" or value == []):
                errors.append(f"{fid} is required")

            if ftype == "path" and value:
                path = Path(str(value))
                must_exist = field.get("must_exist", False)
                kind = field.get("kind")
                if must_exist and not path.exists():
                    errors.append(f"{fid} path does not exist")
                if kind == "file" and path.exists() and not path.is_file():
                    errors.append(f"{fid} must be a file")
                if kind == "dir" and path.exists() and not path.is_dir():
                    errors.append(f"{fid} must be a directory")

            if ftype == "secret" and field.get("source") == "env":
                env_name = field.get("env")
                if env_name:
                    import os

                    value = os.environ.get(env_name, "")
            data[fid] = value

        if errors:
            raise EngineError("\n".join(errors))
        return data

    def run_action(self) -> None:
        if not self.engine:
            return
        try:
            self.output.delete("1.0", "end")
            form = self.collect_form()
            results = self.engine.run_action(self.action_var.get(), form, self.log)
            self.log("Done")
            self.log(json.dumps(results, ensure_ascii=False, indent=2))
        except Exception as exc:
            messagebox.showerror("Execution error", str(exc))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="YAML-driven CLI UI")
    parser.add_argument("config", nargs="?", default="examples/yt_audio.yaml")
    args = parser.parse_args()

    app = App(args.config)
    app.mainloop()


if __name__ == "__main__":
    main()
