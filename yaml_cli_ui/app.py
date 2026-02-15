from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

from .engine import EngineError, PipelineEngine, validate_config


IDLE_COLOR = "#d9d9d9"
RUNNING_COLOR = "#f1c40f"
SUCCESS_COLOR = "#2ecc71"
FAILED_COLOR = "#e74c3c"


class App(tk.Tk):
    def __init__(self, config_path: str):
        super().__init__()
        self.title("YAML CLI UI")
        self.geometry("980x700")
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.engine: PipelineEngine | None = None
        self.run_seq = 0

        self.run_records: dict[int, dict[str, Any]] = {}
        self.action_histories: dict[str, list[int]] = {}
        self.action_history_vars: dict[str, tk.StringVar] = {}
        self.action_history_combos: dict[str, ttk.Combobox] = {}
        self.action_output_texts: dict[str, tk.Text] = {}
        self.action_buttons: dict[str, tk.Button] = {}
        self.action_running_counts: dict[str, int] = {}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="YAML file:").pack(side="left")
        self.path_entry = ttk.Entry(top)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.insert(0, str(self.config_path))
        ttk.Button(top, text="Browse", command=self._browse).pack(side="left", padx=4)
        ttk.Button(top, text="Reload", command=self.load_config).pack(side="left")

        action_row = ttk.Frame(self)
        action_row.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(action_row, text="Actions:").pack(anchor="w")
        self.actions_frame = ttk.Frame(action_row)
        self.actions_frame.pack(fill="x", pady=(4, 0))

        ttk.Label(self, text="Output:").pack(anchor="w", padx=10)
        self.output_notebook = ttk.Notebook(self)
        self.output_notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        aggregate_frame = ttk.Frame(self.output_notebook)
        self.output_notebook.add(aggregate_frame, text="All runs")
        self.aggregate_output = tk.Text(aggregate_frame, height=14)
        self.aggregate_output.pack(fill="both", expand=True)

        self.load_config()

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml")])
        if selected:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, selected)
            self.load_config()

    def _run_label(self, run_id: int) -> str:
        run = self.run_records[run_id]
        return f"#{run_id} [{run['started_at']}] {run['status']}"

    def _append_run_log(self, run_id: int, msg: str) -> None:
        run = self.run_records[run_id]
        run["lines"].append(msg)
        aggregate_line = f"[{run['action']}#{run_id}] {msg}"
        self.aggregate_output.insert("end", aggregate_line + "\n")
        self.aggregate_output.see("end")

        action_id = run["action"]
        selected = self.action_history_vars[action_id].get()
        if selected == self._run_label(run_id):
            text = self.action_output_texts[action_id]
            text.insert("end", msg + "\n")
            text.see("end")
        self.update_idletasks()

    def _render_action_run(self, action_id: str, run_id: int) -> None:
        run = self.run_records[run_id]
        text = self.action_output_texts[action_id]
        text.delete("1.0", "end")
        for line in run["lines"]:
            text.insert("end", line + "\n")
        text.see("end")

    def _select_action_run(self, action_id: str, run_id: int) -> None:
        var = self.action_history_vars[action_id]
        var.set(self._run_label(run_id))
        self._render_action_run(action_id, run_id)

    def _on_history_selected(self, action_id: str) -> None:
        selected = self.action_history_vars[action_id].get()
        for run_id in self.action_histories.get(action_id, []):
            if selected == self._run_label(run_id):
                self._render_action_run(action_id, run_id)
                return

    def _refresh_action_history(self, action_id: str) -> None:
        combo = self.action_history_combos[action_id]
        values = [self._run_label(run_id) for run_id in self.action_histories.get(action_id, [])]
        combo["values"] = values

    def _create_action_tab(self, action_id: str) -> None:
        tab = ttk.Frame(self.output_notebook)
        self.output_notebook.add(tab, text=action_id)

        row = ttk.Frame(tab)
        row.pack(fill="x", padx=4, pady=4)
        ttk.Label(row, text="History:").pack(side="left")

        var = tk.StringVar()
        combo = ttk.Combobox(row, state="readonly", textvariable=var)
        combo.pack(side="left", fill="x", expand=True, padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e, aid=action_id: self._on_history_selected(aid))

        output = tk.Text(tab, height=12)
        output.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.action_history_vars[action_id] = var
        self.action_history_combos[action_id] = combo
        self.action_output_texts[action_id] = output

    def _rebuild_action_tabs(self) -> None:
        for tab_id in self.output_notebook.tabs()[1:]:
            self.output_notebook.forget(tab_id)
        self.action_history_vars.clear()
        self.action_history_combos.clear()
        self.action_output_texts.clear()

        for action_id in self.config.get("actions", {}).keys():
            self._create_action_tab(action_id)

    def _set_action_status(self, action_id: str, status: str) -> None:
        color = {
            "idle": IDLE_COLOR,
            "running": RUNNING_COLOR,
            "success": SUCCESS_COLOR,
            "failed": FAILED_COLOR,
        }.get(status, IDLE_COLOR)
        btn = self.action_buttons.get(action_id)
        if btn is not None:
            btn.configure(bg=color, activebackground=color)

    def _new_run(self, action_id: str) -> int:
        self.run_seq += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        run_id = self.run_seq
        run = {
            "id": run_id,
            "action": action_id,
            "status": "running",
            "started_at": timestamp,
            "lines": [],
            "result": None,
            "error": None,
        }
        self.run_records[run_id] = run
        self.action_histories.setdefault(action_id, []).append(run_id)
        self._refresh_action_history(action_id)
        self._select_action_run(action_id, run_id)

        self.action_running_counts[action_id] = self.action_running_counts.get(action_id, 0) + 1
        self._set_action_status(action_id, "running")
        return run_id

    def _build_action_buttons(self) -> None:
        for child in self.actions_frame.winfo_children():
            child.destroy()
        self.action_buttons.clear()

        actions = self.config.get("actions", {})
        for index, (action_id, action) in enumerate(actions.items()):
            title = action.get("title", action_id)
            btn = tk.Button(
                self.actions_frame,
                text=title,
                bg=IDLE_COLOR,
                activebackground=IDLE_COLOR,
                command=lambda aid=action_id: self.open_action_dialog(aid),
            )
            btn.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
            self.action_buttons[action_id] = btn

        for col in range(4):
            self.actions_frame.columnconfigure(col, weight=1)

    def load_config(self) -> None:
        try:
            self.config_path = Path(self.path_entry.get())
            self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
            validate_config(self.config)
            self.engine = PipelineEngine(self.config)
            title = self.config.get("app", {}).get("title", "YAML CLI UI")
            self.title(title)
            actions = self.config.get("actions", {})
            self.run_records.clear()
            self.action_histories = {aid: [] for aid in actions.keys()}
            self.action_running_counts = {aid: 0 for aid in actions.keys()}
            self.run_seq = 0
            self.aggregate_output.delete("1.0", "end")
            self._build_action_buttons()
            self._rebuild_action_tabs()
            self.aggregate_output.insert("end", f"Loaded: {self.config_path}\n")
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))

    def _create_form_fields(self, parent: tk.Widget, form: dict[str, Any]) -> dict[str, tuple[dict[str, Any], Any]]:
        fields: dict[str, tuple[dict[str, Any], Any]] = {}
        for i, field in enumerate(form.get("fields", [])):
            fid = field["id"]
            label = field.get("label", fid)
            ftype = field.get("type", "string")
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=4)

            widget: Any
            if ftype in {"string", "path", "int", "float", "secret"}:
                show = "*" if ftype == "secret" and field.get("source", "inline") == "inline" else ""
                widget = ttk.Entry(parent, show=show)
                if "default" in field:
                    widget.insert(0, str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "text":
                widget = tk.Text(parent, height=4)
                if "default" in field:
                    widget.insert("1.0", str(field["default"]))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "bool":
                var = tk.BooleanVar(value=bool(field.get("default", False)))
                widget = ttk.Checkbutton(parent, variable=var)
                widget.var = var
                widget.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            elif ftype == "tri_bool":
                widget = ttk.Combobox(parent, state="readonly", values=["auto", "true", "false"])
                widget.set(field.get("default", "auto"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "choice":
                widget = ttk.Combobox(parent, state="readonly", values=field.get("options", []))
                if field.get("default") is not None:
                    widget.set(field.get("default"))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "multichoice":
                widget = tk.Listbox(parent, selectmode="multiple", height=5, exportselection=False)
                for opt in field.get("options", []):
                    widget.insert("end", opt)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype in {"kv_list", "struct_list"}:
                widget = tk.Text(parent, height=5)
                if "default" in field:
                    widget.insert("1.0", json.dumps(field["default"], ensure_ascii=False, indent=2))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                ttk.Label(parent, text="JSON/YAML list input").grid(row=i, column=2, sticky="w")
            else:
                widget = ttk.Entry(parent)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            fields[fid] = (field, widget)
        parent.columnconfigure(1, weight=1)
        return fields

    def _collect_form(self, fields: dict[str, tuple[dict[str, Any], Any]]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        errors: list[str] = []
        for fid, (field, widget) in fields.items():
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

    def _run_action_worker(self, run_id: int, action_id: str, form: dict[str, Any]) -> None:
        assert self.engine is not None

        def logger(msg: str) -> None:
            self.after(0, self._append_run_log, run_id, msg)

        try:
            results = self.engine.run_action(action_id, form, logger)
            self.after(0, self._finish_run, run_id, True, results, None)
        except Exception as exc:
            self.after(0, self._finish_run, run_id, False, None, str(exc))

    def _finish_run(self, run_id: int, success: bool, results: dict[str, Any] | None, error: str | None) -> None:
        run = self.run_records[run_id]
        action_id = run["action"]

        if success:
            run["status"] = "done"
            run["result"] = results
            self._append_run_log(run_id, "Done")
            self._append_run_log(run_id, json.dumps(results, ensure_ascii=False, indent=2))
        else:
            run["status"] = "failed"
            run["error"] = error
            self._append_run_log(run_id, f"[error] {error}")
            messagebox.showerror("Execution error", error or "Unknown error")

        self.action_running_counts[action_id] = max(0, self.action_running_counts.get(action_id, 1) - 1)
        if self.action_running_counts[action_id] > 0:
            self._set_action_status(action_id, "running")
        else:
            self._set_action_status(action_id, "success" if success else "failed")

        self._refresh_action_history(action_id)
        self._on_history_selected(action_id)

    def _start_action(self, action_id: str, form: dict[str, Any]) -> None:
        run_id = self._new_run(action_id)
        self._append_run_log(run_id, "Started")
        worker = threading.Thread(target=self._run_action_worker, args=(run_id, action_id, form), daemon=True)
        worker.start()

    def open_action_dialog(self, action_id: str) -> None:
        if not self.engine:
            return

        action = self.config.get("actions", {}).get(action_id, {})
        form = action.get("form", {})

        dialog = tk.Toplevel(self)
        dialog.title(action.get("title", action_id))
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("700x500")

        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        fields = self._create_form_fields(body, form)

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=10, pady=(0, 10))

        def on_run() -> None:
            try:
                data = self._collect_form(fields)
            except Exception as exc:
                messagebox.showerror("Execution error", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._start_action(action_id, data)

        ttk.Button(actions, text="Run", command=on_run).pack(side="right")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))

    def mainloop(self, n: int = 0) -> None:
        super().mainloop(n)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="YAML-driven CLI UI")
    parser.add_argument("config", nargs="?", default="examples/yt_audio.yaml")
    args = parser.parse_args()

    app = App(args.config)
    app.mainloop()


if __name__ == "__main__":
    main()
