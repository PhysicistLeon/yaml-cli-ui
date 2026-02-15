from __future__ import annotations

import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

from .engine import EngineError, PipelineEngine, validate_config


class ActionFormDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, action_id: str, action: dict[str, Any]):
        super().__init__(parent)
        self.title(action.get("title", action_id))
        self.transient(parent)
        self.grab_set()
        self.result: dict[str, Any] | None = None
        self.fields: dict[str, tuple[dict[str, Any], Any]] = {}

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        form = action.get("form", {})
        for i, field in enumerate(form.get("fields", [])):
            fid = field["id"]
            label = field.get("label", fid)
            ftype = field.get("type", "string")
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=4)

            widget: Any
            if ftype in {"string", "path", "int", "float", "secret"}:
                show = "*" if ftype == "secret" and field.get("source", "inline") == "inline" else ""
                widget = ttk.Entry(frame, show=show)
                if "default" in field:
                    widget.insert(0, str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "text":
                widget = tk.Text(frame, height=4)
                if "default" in field:
                    widget.insert("1.0", str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "bool":
                var = tk.BooleanVar(value=bool(field.get("default", False)))
                widget = ttk.Checkbutton(frame, variable=var)
                widget.var = var
                widget.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            elif ftype == "tri_bool":
                widget = ttk.Combobox(frame, state="readonly", values=["auto", "true", "false"])
                widget.set(field.get("default", "auto"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "choice":
                widget = ttk.Combobox(frame, state="readonly", values=field.get("options", []))
                if field.get("default") is not None:
                    widget.set(field.get("default"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "multichoice":
                widget = tk.Listbox(frame, selectmode="multiple", height=5, exportselection=False)
                for opt in field.get("options", []):
                    widget.insert("end", opt)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype in {"kv_list", "struct_list"}:
                widget = tk.Text(frame, height=5)
                if "default" in field:
                    widget.insert("1.0", json.dumps(field["default"], ensure_ascii=False, indent=2))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                ttk.Label(frame, text="JSON/YAML list input").grid(row=i, column=2, sticky="w")
            else:
                widget = ttk.Entry(frame)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            self.fields[fid] = (field, widget)

        frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=4)
        ttk.Button(buttons, text="Run", command=self._submit).pack(side="right")

        self.bind("<Escape>", lambda _e: self._cancel())

    def _collect_form(self) -> dict[str, Any]:
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

    def _submit(self) -> None:
        try:
            self.result = self._collect_form()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Execution error", str(exc), parent=self)

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class App(tk.Tk):
    def __init__(self, config_path: str):
        super().__init__()
        self.title("YAML CLI UI")
        self.geometry("980x700")
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.engine: PipelineEngine | None = None
        self.is_running = False
        self.active_action: str | None = None

        self.action_buttons: dict[str, tk.Button] = {}
        self.button_default_bg: dict[str, str] = {}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="YAML file:").pack(side="left")
        self.path_entry = ttk.Entry(top)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.insert(0, str(self.config_path))
        ttk.Button(top, text="Browse", command=self._browse).pack(side="left", padx=4)
        ttk.Button(top, text="Reload", command=self.load_config).pack(side="left")

        ttk.Label(self, text="Actions:").pack(anchor="w", padx=10)
        self.actions_frame = ttk.Frame(self)
        self.actions_frame.pack(fill="x", padx=10, pady=(2, 10))

        ttk.Label(self, text="Output:").pack(anchor="w", padx=10)
        self.output = tk.Text(self, height=18)
        self.output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.load_config()

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml")])
        if selected:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, selected)
            self.load_config()

    def _append_log(self, msg: str) -> None:
        self.output.insert("end", msg + "\n")
        self.output.see("end")
        self.update_idletasks()

    def log(self, msg: str) -> None:
        self.after(0, self._append_log, msg)

    def _build_action_buttons(self) -> None:
        for child in self.actions_frame.winfo_children():
            child.destroy()
        self.action_buttons.clear()
        self.button_default_bg.clear()

        actions = self.config.get("actions", {})
        for idx, (action_id, action) in enumerate(actions.items()):
            title = action.get("title", action_id)
            btn = tk.Button(
                self.actions_frame,
                text=title,
                command=lambda aid=action_id: self.run_action(aid),
                padx=12,
                pady=6,
            )
            btn.grid(row=0, column=idx, padx=(0, 8), pady=4, sticky="w")
            self.action_buttons[action_id] = btn
            self.button_default_bg[action_id] = btn.cget("bg")

    def _set_button_color(self, action_id: str, color: str | None) -> None:
        button = self.action_buttons.get(action_id)
        if not button:
            return
        if color is None:
            color = self.button_default_bg.get(action_id, button.cget("bg"))
        button.config(bg=color, activebackground=color, fg="white" if color in {"red", "green"} else "black")

    def _set_running(self, running: bool) -> None:
        self.is_running = running
        state = "disabled" if running else "normal"
        for btn in self.action_buttons.values():
            btn.config(state=state)

    def _prompt_action_form(self, action_id: str) -> dict[str, Any] | None:
        action = self.config.get("actions", {}).get(action_id, {})
        fields = action.get("form", {}).get("fields", [])
        if not fields:
            return {}
        dialog = ActionFormDialog(self, action_id, action)
        self.wait_window(dialog)
        return dialog.result

    def load_config(self) -> None:
        try:
            self.config_path = Path(self.path_entry.get())
            self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
            validate_config(self.config)
            self.engine = PipelineEngine(self.config)
            title = self.config.get("app", {}).get("title", "YAML CLI UI")
            self.title(title)
            self._build_action_buttons()
            self.log(f"Loaded: {self.config_path}")
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))

    def _finish_action(self, action_id: str) -> None:
        self._set_button_color(action_id, "green")
        self._set_running(False)
        self.active_action = None

    def _run_action_worker(self, action_id: str, form: dict[str, Any]) -> None:
        assert self.engine is not None
        try:
            results = self.engine.run_action(action_id, form, self.log)
            self.log("Done")
            self.log(json.dumps(results, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.after(0, messagebox.showerror, "Execution error", str(exc))
        finally:
            self.after(0, self._finish_action, action_id)

    def run_action(self, action_id: str) -> None:
        if not self.engine or self.is_running:
            return

        form = self._prompt_action_form(action_id)
        if form is None:
            return

        self.output.delete("1.0", "end")
        self._set_running(True)
        self.active_action = action_id
        self._set_button_color(action_id, "red")
        worker = threading.Thread(target=self._run_action_worker, args=(action_id, form), daemon=True)
        worker.start()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="YAML-driven CLI UI")
    parser.add_argument("config", nargs="?", default="examples/yt_audio.yaml")
    args = parser.parse_args()

    app = App(args.config)
    app.mainloop()


if __name__ == "__main__":
    main()
