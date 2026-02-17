from __future__ import annotations

import argparse
import configparser
import json
import os
import threading
from copy import deepcopy
from functools import partial
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import yaml

from .engine import ActionCancelledError, EngineError, PipelineEngine, validate_config
from .presets import PresetError, PresetService


IDLE_COLOR = "#d9d9d9"
RUNNING_COLOR = "#f1c40f"
SUCCESS_COLOR = "#2ecc71"
FAILED_COLOR = "#e74c3c"
DEFAULT_CONFIG_PATH = "examples/yt_audio.yaml"
STATE_FILE_PATH = Path.home() / ".yaml_cli_ui" / "state.json"


HELP_CONTENT = """Как работает приложение
1. Выберите YAML-файл с описанием приложения и действий.
2. Нажмите Reload, чтобы перечитать конфигурацию и обновить кнопки действий.
3. Нажмите кнопку действия, заполните форму и нажмите Run.
4. Следите за логами во вкладке All runs и во вкладке конкретного действия.

Как писать YAML (примеры)
Минимальный пример:

app:
  title: "Demo YAML CLI UI"
actions:
  hello:
    title: "Сказать привет"
    form:
      fields:
        - id: name
          label: "Имя"
          type: string
          required: true
    pipeline:
      - run:
          cmd: "echo Привет, {{ form.name }}!"

Пример с выбором файлов и параметров:

actions:
  convert:
    title: "Конвертация"
    form:
      fields:
        - id: input_file
          label: "Входной файл"
          type: path
          kind: file
          must_exist: true
        - id: output_dir
          label: "Папка результата"
          type: path
          kind: dir
          must_exist: true
        - id: bitrate
          label: "Битрейт"
          type: int
          widget: spinbox
          min: 64
          max: 320
          step: 32
          default: 192

FAQ
Q: Почему кнопка действия стала жёлтой?
A: Это статус running — действие выполняется.

Q: Что означает красный цвет кнопки?
A: Выполнение завершилось с ошибкой, подробности смотрите в логах.

Q: Можно ли хранить секреты в YAML?
A: Лучше использовать поля secret c source: env и передавать секреты через переменные окружения.

Q: Почему не открывается файл из Browse?
A: Проверьте browse_dir в app.ini, права доступа и существование директории/файла.
"""


def _resolve_ini_path(value: str, ini_path: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = (ini_path.parent / candidate).resolve()
    return candidate


def load_launch_settings(ini_path: str | None) -> dict[str, Path | None]:
    settings: dict[str, Path | None] = {"default_yaml": None, "browse_dir": None}
    if not ini_path:
        return settings

    config = configparser.ConfigParser()
    parsed = config.read(ini_path, encoding="utf-8")
    if not parsed:
        raise FileNotFoundError(f"Settings file was not found: {ini_path}")

    resolved_ini_path = Path(parsed[0]).resolve()
    ui_section = config["ui"] if config.has_section("ui") else {}

    default_yaml = str(ui_section.get("default_yaml", "")).strip()
    if default_yaml:
        settings["default_yaml"] = _resolve_ini_path(default_yaml, resolved_ini_path)

    browse_dir = str(ui_section.get("browse_dir", "")).strip()
    if browse_dir:
        settings["browse_dir"] = _resolve_ini_path(browse_dir, resolved_ini_path)

    return settings


def _decimal_places(value: Any) -> int:
    if not isinstance(value, (int, float)):
        return 0
    text = format(Decimal(str(value)).normalize(), "f")
    if "." not in text:
        return 0
    return len(text.rstrip("0").split(".", 1)[1])


def slider_scale_for_float_field(field: dict[str, Any]) -> int:
    candidates = [
        field.get("step"),
        field.get("default"),
        field.get("min"),
        field.get("max"),
    ]
    decimals = max((_decimal_places(v) for v in candidates), default=0)
    return 10**decimals


def load_ui_state(state_file: Path = STATE_FILE_PATH) -> dict[str, Any]:
    if not state_file.exists():
        return {}
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_ui_state(state: dict[str, Any], state_file: Path = STATE_FILE_PATH) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class App(tk.Tk):
    def __init__(self, config_path: str, browse_dir: str | Path | None = None):
        super().__init__()
        self.title("YAML CLI UI")
        self.geometry("980x700")
        self.config_path = Path(config_path)
        self.browse_dir = Path(browse_dir) if browse_dir else None
        self.app_config: dict[str, Any] = {}
        self.engine: PipelineEngine | None = None
        self.run_seq = 0

        self.run_records: dict[int, dict[str, Any]] = {}
        self.action_histories: dict[str, list[int]] = {}
        self.action_history_vars: dict[str, tk.StringVar] = {}
        self.action_history_combos: dict[str, ttk.Combobox] = {}
        self.action_output_texts: dict[str, tk.Text] = {}
        self.action_buttons: dict[str, tk.Button] = {}
        self.action_running_counts: dict[str, int] = {}
        self.ui_state = load_ui_state()
        self.preset_service = PresetService(self.config_path)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        self._build_menu()
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

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="Помощь", command=self._open_help_window)
        menu_bar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=menu_bar)

    def _open_help_window(self) -> None:
        help_window = tk.Toplevel(self)
        help_window.title("Помощь")
        help_window.transient(self)
        help_window.geometry("800x600")

        frame = ttk.Frame(help_window)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        text = tk.Text(frame, wrap="word")
        text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.configure(yscrollcommand=scrollbar.set)

        text.insert("1.0", HELP_CONTENT)
        text.configure(state="disabled")

    def _browse(self) -> None:
        browse_kwargs: dict[str, Any] = {"filetypes": [("YAML", "*.yaml *.yml")]}
        if self.browse_dir:
            browse_kwargs["initialdir"] = str(self.browse_dir)

        selected = filedialog.askopenfilename(**browse_kwargs)
        if selected:
            self.browse_dir = Path(selected).parent
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, selected)
            self.load_config()

    def _pick_path(self, field: dict[str, Any], entry: ttk.Entry) -> None:
        kind = field.get("kind")
        current_value = entry.get().strip()
        current_path = Path(current_value).expanduser() if current_value else None

        initialdir: str | None = None
        if current_path:
            if current_path.exists() and current_path.is_dir():
                initialdir = str(current_path)
            else:
                initialdir = str(current_path.parent)
        elif self.browse_dir:
            initialdir = str(self.browse_dir)

        if kind == "dir":
            selected = (
                filedialog.askdirectory(initialdir=initialdir)
                if initialdir
                else filedialog.askdirectory()
            )
        else:
            dialog_kwargs: dict[str, Any] = {}
            if initialdir:
                dialog_kwargs["initialdir"] = initialdir
            selected = filedialog.askopenfilename(**dialog_kwargs)

        if selected:
            selected_path = Path(selected)
            if selected_path.exists():
                self.browse_dir = (
                    selected_path if selected_path.is_dir() else selected_path.parent
                )
            entry.delete(0, "end")
            entry.insert(0, selected)

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
        values = [
            self._run_label(run_id)
            for run_id in self.action_histories.get(action_id, [])
        ]
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
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e, aid=action_id: self._on_history_selected(aid),
        )

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

        for action_id in self.app_config.get("actions", {}).keys():
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

        self.action_running_counts[action_id] = (
            self.action_running_counts.get(action_id, 0) + 1
        )
        self._set_action_status(action_id, "running")
        return run_id

    def _build_action_buttons(self) -> None:
        for child in self.actions_frame.winfo_children():
            child.destroy()
        self.action_buttons.clear()

        actions = self.app_config.get("actions", {})
        for index, (action_id, action) in enumerate(actions.items()):
            title = action.get("title", action_id)
            btn = tk.Button(
                self.actions_frame,
                text=title,
                bg=IDLE_COLOR,
                activebackground=IDLE_COLOR,
                command=lambda aid=action_id: self._on_action_button_click(aid),
            )
            btn.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
            self.action_buttons[action_id] = btn

        for col in range(4):
            self.actions_frame.columnconfigure(col, weight=1)

    def _config_state_key(self) -> str:
        return str(self.config_path.resolve())

    def _get_saved_form_values(self, action_id: str) -> dict[str, Any]:
        config_state = self.ui_state.get(self._config_state_key(), {})
        if not isinstance(config_state, dict):
            return {}
        action_state = config_state.get(action_id, {})
        return action_state if isinstance(action_state, dict) else {}

    def _save_form_values(self, action_id: str, values: dict[str, Any]) -> None:
        key = self._config_state_key()
        config_state = self.ui_state.get(key)
        if not isinstance(config_state, dict):
            config_state = {}
            self.ui_state[key] = config_state
        config_state[action_id] = values
        try:
            save_ui_state(self.ui_state)
        except OSError:
            pass

    def load_config(self) -> None:
        try:
            self.config_path = Path(self.path_entry.get())
            self.preset_service = PresetService(self.config_path)
            self.app_config = yaml.safe_load(
                self.config_path.read_text(encoding="utf-8")
            )
            validate_config(self.app_config)
            self.engine = PipelineEngine(self.app_config)
            title = self.app_config.get("app", {}).get("title", "YAML CLI UI")
            self.title(title)
            actions = self.app_config.get("actions", {})
            self.run_records.clear()
            self.action_histories = {aid: [] for aid in actions.keys()}
            self.action_running_counts = {aid: 0 for aid in actions.keys()}
            self.run_seq = 0
            self.aggregate_output.delete("1.0", "end")
            self._build_action_buttons()
            self._rebuild_action_tabs()
            self.aggregate_output.insert("end", f"Loaded: {self.config_path}\n")
        except (OSError, yaml.YAMLError, EngineError, TypeError, ValueError) as exc:
            messagebox.showerror("Config error", str(exc))

    @staticmethod
    def _sync_slider_raw_value(
        raw_value: int,
        *,
        state: dict[str, bool],
        normalize: Any,
        slider: tk.Scale,
        to_text: Any,
        value_var: tk.StringVar,
        value_label: ttk.Label | None,
    ) -> None:
        if state["syncing"]:
            return
        state["syncing"] = True
        normalized = normalize(raw_value)
        slider.set(normalized)
        text_value = to_text(normalized)
        value_var.set(text_value)
        if value_label is not None:
            value_label.configure(text=text_value)
        state["syncing"] = False

    @staticmethod
    def _on_slider_change(raw_text: str, *, sync: Any) -> None:
        sync(int(float(raw_text)))

    @staticmethod
    def _on_slider_entry_commit(
        _event: tk.Event[Any] | None = None,
        *,
        state: dict[str, bool],
        value_var: tk.StringVar,
        sync: Any,
        slider: tk.Scale,
        scale: int,
    ) -> None:
        if state["syncing"]:
            return
        try:
            entered_value = float(value_var.get().strip())
        except ValueError:
            sync(int(slider.get()))
            return
        sync(int(round(entered_value * scale)))

    def _create_form_fields(
        self,
        parent: tk.Widget,
        form: dict[str, Any],
        initial_values: dict[str, Any] | None = None,
    ) -> dict[str, tuple[dict[str, Any], Any]]:
        fields: dict[str, tuple[dict[str, Any], Any]] = {}
        initial_values = initial_values or {}
        for i, field in enumerate(form.get("fields", [])):
            fid = field["id"]
            label = field.get("label", fid)
            ftype = field.get("type", "string")
            widget_hint = field.get("widget")
            initial_value = initial_values.get(fid, field.get("default"))
            slider_opts = (
                field.get("slider", {}) if isinstance(field.get("slider"), dict) else {}
            )
            ttk.Label(parent, text=label).grid(
                row=i, column=0, sticky="w", padx=5, pady=4
            )

            widget: Any
            if (
                ftype in {"int", "float"}
                and widget_hint == "slider"
                and "min" in field
                and "max" in field
            ):
                scale = slider_scale_for_float_field(field) if ftype == "float" else 1
                min_value = int(round(float(field["min"]) * scale))
                max_value = int(round(float(field["max"]) * scale))
                step_value = max(
                    1,
                    int(
                        round(
                            float(field.get("step", 1 if ftype == "int" else 0.1))
                            * scale
                        )
                    ),
                )
                default_raw = (
                    initial_value if initial_value is not None else field.get("min", 0)
                )
                display_decimals = (
                    _decimal_places(field.get("step", 0)) if ftype == "float" else 0
                )

                wrapper = ttk.Frame(parent)
                wrapper.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                wrapper.columnconfigure(0, weight=1)

                slider = tk.Scale(
                    wrapper,
                    from_=min_value,
                    to=max_value,
                    orient="horizontal",
                    resolution=step_value,
                    showvalue=False,
                    tickinterval=step_value if slider_opts.get("ticks") else 0,
                )
                slider.grid(row=0, column=0, sticky="ew")

                min_label = ttk.Label(wrapper, text=str(field["min"]))
                min_label.grid(row=1, column=0, sticky="w")
                max_label = ttk.Label(wrapper, text=str(field["max"]))
                max_label.grid(row=1, column=0, sticky="e")

                value_var = tk.StringVar()
                value_entry = ttk.Entry(wrapper, textvariable=value_var, width=12)
                value_entry.grid(row=0, column=1, padx=(8, 0), sticky="e")

                value_label: ttk.Label | None = None
                if slider_opts.get("show_value"):
                    value_label = ttk.Label(wrapper)
                    value_label.grid(row=1, column=1, padx=(8, 0), sticky="e")

                state = {"syncing": False}

                def _scaled_to_text(
                    raw_value: int,
                    *,
                    _scale: int = scale,
                    _ftype: str = ftype,
                    _display_decimals: int = display_decimals,
                ) -> str:
                    shown = raw_value / _scale
                    if _ftype == "int":
                        return str(int(round(shown)))
                    return (
                        f"{shown:.{_display_decimals}f}"
                        if _display_decimals > 0
                        else str(shown)
                    )

                def _normalize_raw(
                    raw_value: int,
                    *,
                    _min_value: int = min_value,
                    _max_value: int = max_value,
                    _step_value: int = step_value,
                ) -> int:
                    bounded = max(_min_value, min(_max_value, raw_value))
                    snapped = (
                        _min_value
                        + int(round((bounded - _min_value) / _step_value)) * _step_value
                    )
                    return max(_min_value, min(_max_value, snapped))

                sync_from_raw = partial(
                    self._sync_slider_raw_value,
                    state=state,
                    normalize=_normalize_raw,
                    slider=slider,
                    to_text=_scaled_to_text,
                    value_var=value_var,
                    value_label=value_label,
                )
                slider_change_handler = partial(
                    self._on_slider_change, sync=sync_from_raw
                )
                entry_commit_handler = partial(
                    self._on_slider_entry_commit,
                    state=state,
                    value_var=value_var,
                    sync=sync_from_raw,
                    slider=slider,
                    scale=scale,
                )

                slider.configure(command=slider_change_handler)
                value_entry.bind("<Return>", entry_commit_handler)
                value_entry.bind("<FocusOut>", entry_commit_handler)

                sync_from_raw(int(round(float(default_raw) * scale)))

                widget = {
                    "kind": "slider",
                    "control": slider,
                    "scale": scale,
                    "type": ftype,
                }
            elif ftype in {"string", "int", "float", "secret"}:
                show = (
                    "*"
                    if ftype == "secret" and field.get("source", "inline") == "inline"
                    else ""
                )
                if (
                    ftype in {"int", "float"}
                    and widget_hint == "spinbox"
                    and "min" in field
                    and "max" in field
                ):
                    increment = field.get("step", 1 if ftype == "int" else 0.1)
                    widget = ttk.Spinbox(
                        parent, from_=field["min"], to=field["max"], increment=increment
                    )
                else:
                    widget = ttk.Entry(parent, show=show)
                if initial_value is not None:
                    widget.insert(0, str(initial_value))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "path":
                path_wrapper = ttk.Frame(parent)
                path_wrapper.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                path_wrapper.columnconfigure(0, weight=1)

                widget = ttk.Entry(path_wrapper)
                if initial_value is not None:
                    widget.insert(0, str(initial_value))
                widget.grid(row=0, column=0, sticky="ew")

                ttk.Button(
                    path_wrapper,
                    text="Browse…",
                    command=lambda _f=field, _entry=widget: self._pick_path(_f, _entry),
                ).grid(row=0, column=1, padx=(6, 0))
            elif ftype == "text":
                widget = tk.Text(parent, height=4)
                if initial_value is not None:
                    widget.insert("1.0", str(initial_value))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "bool":
                var = tk.BooleanVar(
                    value=bool(initial_value) if initial_value is not None else False
                )
                widget = ttk.Checkbutton(parent, variable=var)
                widget.var = var
                widget.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            elif ftype == "tri_bool":
                widget = ttk.Combobox(
                    parent, state="readonly", values=["auto", "true", "false"]
                )
                widget.set(str(initial_value) if initial_value is not None else "auto")
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "choice":
                widget = ttk.Combobox(
                    parent, state="readonly", values=field.get("options", [])
                )
                if initial_value is not None:
                    widget.set(str(initial_value))
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype == "multichoice":
                widget = tk.Listbox(
                    parent, selectmode="multiple", height=5, exportselection=False
                )
                options = field.get("options", [])
                for opt in options:
                    widget.insert("end", opt)
                if isinstance(initial_value, list):
                    for idx, opt in enumerate(options):
                        if opt in initial_value:
                            widget.selection_set(idx)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            elif ftype in {"kv_list", "struct_list"}:
                widget = tk.Text(parent, height=5)
                if initial_value is not None:
                    widget.insert(
                        "1.0", json.dumps(initial_value, ensure_ascii=False, indent=2)
                    )
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
                ttk.Label(parent, text="JSON/YAML list input").grid(
                    row=i, column=2, sticky="w"
                )
            else:
                widget = ttk.Entry(parent)
                widget.grid(row=i, column=1, sticky="ew", padx=5, pady=4)
            fields[fid] = (field, widget)
        parent.columnconfigure(1, weight=1)
        return fields

    def _collect_form(
        self, fields: dict[str, tuple[dict[str, Any], Any]]
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        errors: list[str] = []
        for fid, (field, widget) in fields.items():
            ftype = field.get("type", "string")
            value: Any = None
            if ftype == "text":
                value = widget.get("1.0", "end").rstrip("\n")
            elif isinstance(widget, dict) and widget.get("kind") == "slider":
                scale = widget["scale"]
                raw_value = int(widget["control"].get())
                value = raw_value if scale == 1 else raw_value / scale
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
                    value = os.environ.get(env_name, "")
            data[fid] = value

        if errors:
            raise EngineError("\n".join(errors))
        return data

    @staticmethod
    def _persisted_form_values(
        data: dict[str, Any], fields: dict[str, tuple[dict[str, Any], Any]]
    ) -> dict[str, Any]:
        return {
            fid: value
            for fid, value in data.items()
            if fields[fid][0].get("type") != "secret"
        }

    @staticmethod
    def _compatible_preset_values(
        values: dict[str, Any], fields: dict[str, tuple[dict[str, Any], Any]]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return PresetService.map_values_to_form(values, set(fields.keys()))

    @staticmethod
    def _unused_values_text(unused_values: dict[str, Any]) -> str:
        return json.dumps(unused_values, ensure_ascii=False, indent=2)

    def _set_field_value(self, field: dict[str, Any], widget: Any, value: Any) -> None:
        ftype = field.get("type", "string")

        if value is None:
            value = ""

        if isinstance(widget, dict) and widget.get("kind") == "slider":
            scale = widget["scale"]
            control = widget["control"]
            numeric = float(value) if value != "" else 0
            control.set(int(round(numeric * scale)))
            return

        if ftype == "text":
            widget.delete("1.0", "end")
            if value != "":
                widget.insert("1.0", str(value))
            return

        if ftype == "bool":
            widget.var.set(bool(value))
            return

        if ftype == "multichoice":
            widget.selection_clear(0, "end")
            selected = set(value) if isinstance(value, list) else set()
            for idx in range(widget.size()):
                if widget.get(idx) in selected:
                    widget.selection_set(idx)
            return

        if ftype in {"kv_list", "struct_list"}:
            widget.delete("1.0", "end")
            if value != "":
                widget.insert("1.0", json.dumps(value, ensure_ascii=False, indent=2))
            return

        if hasattr(widget, "delete"):
            widget.delete(0, "end")
        if value != "":
            widget.insert(0, str(value))

    def _apply_values_to_form(
        self,
        fields: dict[str, tuple[dict[str, Any], Any]],
        values: dict[str, Any],
    ) -> None:
        for fid, (field, widget) in fields.items():
            target_value = values.get(fid, field.get("default"))
            self._set_field_value(field, widget, target_value)

    def _run_action_worker(
        self, run_id: int, action_id: str, form: dict[str, Any]
    ) -> None:
        assert self.engine is not None

        def logger(msg: str) -> None:
            self.after(0, self._append_run_log, run_id, msg)

        try:
            results = self.engine.run_action(action_id, form, logger)
            self.after(0, self._finish_run, run_id, True, results, None, False)
        except ActionCancelledError as exc:
            self.after(0, self._finish_run, run_id, False, None, str(exc), True)
        except (EngineError, OSError, ValueError, TypeError) as exc:
            self.after(0, self._finish_run, run_id, False, None, str(exc), False)

    def _finish_run(
        self,
        run_id: int,
        success: bool,
        results: dict[str, Any] | None,
        error: str | None,
        cancelled: bool,
    ) -> None:
        run = self.run_records[run_id]
        action_id = run["action"]

        if success:
            run["status"] = "done"
            run["result"] = results
            self._append_run_log(run_id, "Done")
            self._append_run_log(
                run_id, json.dumps(results, ensure_ascii=False, indent=2)
            )
        else:
            run["status"] = "failed"
            run["error"] = error
            self._append_run_log(run_id, f"[error] {error}")
            if not cancelled:
                messagebox.showerror("Execution error", error or "Unknown error")

        self.action_running_counts[action_id] = max(
            0, self.action_running_counts.get(action_id, 1) - 1
        )
        if self.action_running_counts[action_id] > 0:
            self._set_action_status(action_id, "running")
        else:
            self._set_action_status(action_id, "success" if success else "failed")

        self._refresh_action_history(action_id)
        self._on_history_selected(action_id)

    def _start_action(self, action_id: str, form: dict[str, Any]) -> None:
        run_id = self._new_run(action_id)
        self._append_run_log(run_id, "Started")
        worker = threading.Thread(
            target=self._run_action_worker, args=(run_id, action_id, form), daemon=True
        )
        worker.start()

    def _has_editable_fields(self, form: dict[str, Any]) -> bool:
        fields = form.get("fields", [])
        if not isinstance(fields, list):
            return False
        for field in fields:
            if not isinstance(field, dict):
                continue
            if field.get("type") == "secret" and field.get("source") == "env":
                continue
            return True
        return False

    def _on_action_button_click(self, action_id: str) -> None:
        if self.action_running_counts.get(action_id, 0) > 0:
            should_stop = messagebox.askyesno(
                "Stop action",
                "Action is currently running. Stop it?",
                parent=self,
            )
            if should_stop and self.engine is not None:
                self.engine.stop_action(action_id)
            return
        self.open_action_dialog(action_id)

    def open_action_dialog(self, action_id: str) -> None:
        if not self.engine:
            return

        action = self.app_config.get("actions", {}).get(action_id, {})
        form = action.get("form", {})

        if not self._has_editable_fields(form):
            self._start_action(action_id, {})
            return

        dialog = tk.Toplevel(self)
        dialog.title(action.get("title", action_id))
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("700x500")

        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        presets_section = ttk.LabelFrame(body, text="Presets")
        presets_section.pack(fill="x", pady=(0, 8))

        preset_row = ttk.Frame(presets_section)
        preset_row.pack(fill="x", padx=8, pady=6)

        ttk.Label(preset_row, text="Preset:").pack(side="left")
        preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(preset_row, state="readonly", textvariable=preset_var)
        preset_combo.pack(side="left", fill="x", expand=True, padx=(6, 8))

        fields_wrap = ttk.Frame(body)
        fields_wrap.pack(fill="both", expand=True)

        stale_section = ttk.LabelFrame(body, text="Неиспользованные параметры пресета")
        stale_section.pack(fill="x", pady=(8, 0))
        stale_text = tk.Text(stale_section, height=5)
        stale_text.pack(fill="x", padx=6, pady=6)
        stale_text.configure(state="disabled")

        def set_stale_warning(unused_values: dict[str, Any]) -> None:
            stale_text.configure(state="normal")
            stale_text.delete("1.0", "end")
            if unused_values:
                stale_text.insert("1.0", self._unused_values_text(unused_values))
            stale_text.configure(state="disabled")

        saved_values = self._get_saved_form_values(action_id)
        fields = self._create_form_fields(fields_wrap, form, initial_values=saved_values)

        def refresh_preset_combo() -> list[str]:
            names = self.preset_service.list_presets(action_id)
            preset_combo["values"] = ["(last run)", *names]
            return names

        selected_preset_name: dict[str, str | None] = {"name": None}
        selected_preset_values: dict[str, Any] = {}

        def apply_last_run() -> None:
            last_run = self.preset_service.get_last_run(action_id)
            if not last_run and saved_values:
                self._apply_values_to_form(fields, saved_values)
                preset_var.set("(last run)")
                selected_preset_name["name"] = None
                selected_preset_values.clear()
                set_stale_warning({})
                return

            if last_run.get("mode") == "preset_ref":
                preset_name = str(last_run.get("preset_name", ""))
                preset_values = self.preset_service.get_preset_values(action_id, preset_name)
                if preset_values is not None:
                    mapped, unused = self._compatible_preset_values(preset_values, fields)
                    self._apply_values_to_form(fields, mapped)
                    selected_preset_name["name"] = preset_name
                    selected_preset_values.clear()
                    selected_preset_values.update(deepcopy(mapped))
                    preset_var.set(preset_name)
                    set_stale_warning(unused)
                    return
                messagebox.showwarning(
                    "Preset missing",
                    "Last run referenced preset was not found. The form was reset.",
                    parent=dialog,
                )

            snapshot = last_run.get("values", {}) if isinstance(last_run, dict) else {}
            if not isinstance(snapshot, dict):
                snapshot = {}
            mapped, _unused = self._compatible_preset_values(snapshot, fields)
            self._apply_values_to_form(fields, mapped)
            preset_var.set("(last run)")
            selected_preset_name["name"] = None
            selected_preset_values.clear()
            set_stale_warning({})

        def on_preset_selected(_event: tk.Event[Any] | None = None) -> None:
            selected = preset_var.get().strip()
            if selected == "(last run)" or not selected:
                apply_last_run()
                return
            values = self.preset_service.get_preset_values(action_id, selected)
            if values is None:
                messagebox.showerror("Preset error", "Selected preset was not found", parent=dialog)
                refresh_preset_combo()
                apply_last_run()
                return
            mapped, unused = self._compatible_preset_values(values, fields)
            self._apply_values_to_form(fields, mapped)
            selected_preset_name["name"] = selected
            selected_preset_values.clear()
            selected_preset_values.update(deepcopy(mapped))
            set_stale_warning(unused)

        preset_names = refresh_preset_combo()
        preset_combo.bind("<<ComboboxSelected>>", on_preset_selected)
        if preset_names:
            preset_var.set("(last run)")
        apply_last_run()

        def ask_preset_name(title: str, initial: str = "") -> str | None:
            name = simpledialog.askstring("Preset", title, initialvalue=initial, parent=dialog)
            if name is None:
                return None
            normalized = name.strip()
            if not normalized:
                messagebox.showerror("Preset error", "Preset name must not be empty", parent=dialog)
                return None
            return normalized

        def on_create_preset() -> None:
            name = ask_preset_name("Preset name")
            if not name:
                return
            if name in self.preset_service.list_presets(action_id):
                messagebox.showerror("Preset error", "Preset already exists", parent=dialog)
                return
            try:
                data = self._collect_form(fields)
            except EngineError as exc:
                messagebox.showerror("Execution error", str(exc), parent=dialog)
                return
            persisted = self._persisted_form_values(data, fields)
            try:
                self.preset_service.save_preset(action_id, name, persisted)
            except (PresetError, OSError) as exc:
                messagebox.showerror("Preset error", str(exc), parent=dialog)
                return
            refresh_preset_combo()
            preset_var.set(name)
            on_preset_selected()

        def on_overwrite_preset() -> None:
            current = preset_var.get().strip()
            if not current or current == "(last run)":
                messagebox.showerror("Preset error", "Select a named preset first", parent=dialog)
                return
            confirm = messagebox.askyesno(
                "Overwrite preset",
                f"Overwrite preset '{current}' with current form values?",
                parent=dialog,
            )
            if not confirm:
                return
            try:
                data = self._collect_form(fields)
            except EngineError as exc:
                messagebox.showerror("Execution error", str(exc), parent=dialog)
                return
            persisted = self._persisted_form_values(data, fields)
            try:
                self.preset_service.save_preset(action_id, current, persisted)
            except (PresetError, OSError) as exc:
                messagebox.showerror("Preset error", str(exc), parent=dialog)
                return
            on_preset_selected()

        def on_rename_preset() -> None:
            current = preset_var.get().strip()
            if not current or current == "(last run)":
                messagebox.showerror("Preset error", "Select a named preset first", parent=dialog)
                return
            new_name = ask_preset_name("New preset name", current)
            if not new_name or new_name == current:
                return
            try:
                self.preset_service.rename_preset(action_id, current, new_name)
            except (PresetError, OSError) as exc:
                messagebox.showerror("Preset error", str(exc), parent=dialog)
                return
            refresh_preset_combo()
            preset_var.set(new_name)
            on_preset_selected()

        def on_delete_preset() -> None:
            current = preset_var.get().strip()
            if not current or current == "(last run)":
                messagebox.showerror("Preset error", "Select a named preset first", parent=dialog)
                return
            confirm = messagebox.askyesno(
                "Delete preset",
                f"Delete preset '{current}'?",
                parent=dialog,
            )
            if not confirm:
                return
            try:
                last_ref_cleared = self.preset_service.delete_preset(action_id, current)
            except OSError as exc:
                messagebox.showerror("Preset error", str(exc), parent=dialog)
                return
            if last_ref_cleared:
                messagebox.showwarning(
                    "Last run reference cleared",
                    "Deleted preset was referenced by last run. Reference was cleared and the form reset.",
                    parent=dialog,
                )
            refresh_preset_combo()
            apply_last_run()

        preset_actions = ttk.Frame(presets_section)
        preset_actions.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(preset_actions, text="Create", command=on_create_preset).pack(side="left")
        ttk.Button(preset_actions, text="Overwrite", command=on_overwrite_preset).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(preset_actions, text="Rename", command=on_rename_preset).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(preset_actions, text="Delete", command=on_delete_preset).pack(
            side="left", padx=(6, 0)
        )

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=10, pady=(0, 10))

        def on_run() -> None:
            try:
                data = self._collect_form(fields)
            except EngineError as exc:
                messagebox.showerror("Execution error", str(exc), parent=dialog)
                return
            persisted = self._persisted_form_values(data, fields)
            self._save_form_values(action_id, persisted)

            selected_name = selected_preset_name["name"]
            if selected_name and persisted == selected_preset_values:
                try:
                    self.preset_service.save_last_run_preset_ref(action_id, selected_name)
                except OSError:
                    pass
            else:
                try:
                    self.preset_service.save_last_run_snapshot(action_id, persisted)
                except OSError:
                    pass
            dialog.destroy()
            self._start_action(action_id, data)

        ttk.Button(actions, text="Run", command=on_run).pack(side="right")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(
            side="right", padx=(0, 6)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML-driven CLI UI")
    parser.add_argument("config", nargs="?", default=None)
    parser.add_argument(
        "--settings",
        help="Path to INI file with [ui] default_yaml and browse_dir.",
        default="app.ini",
    )
    args = parser.parse_args()

    settings = load_launch_settings(args.settings)
    default_config = settings["default_yaml"] or Path(DEFAULT_CONFIG_PATH)
    config_path = Path(args.config) if args.config else default_config
    browse_dir = settings["browse_dir"]

    app = App(str(config_path), browse_dir=browse_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
