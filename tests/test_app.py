import pytest

from yaml_cli_ui.app import (
    ActionCancelledError,
    App,
    EngineError,
    HELP_CONTENT,
    load_launch_settings,
    load_ui_state,
    save_ui_state,
    slider_scale_for_float_field,
)


def test_slider_scale_for_float_step_precision():
    field = {"type": "float", "min": 0, "max": 1, "step": 0.05}
    assert slider_scale_for_float_field(field) == 100


def test_slider_scale_uses_max_decimal_places_from_numeric_props():
    field = {"type": "float", "min": 0.001, "max": 1, "default": 0.25}
    assert slider_scale_for_float_field(field) == 1000


def test_load_launch_settings_reads_default_yaml_and_browse_dir(tmp_path):
    settings_file = tmp_path / "ui.ini"
    settings_file.write_text(
        "[ui]\ndefault_yaml = configs/main.yaml\nbrowse_dir = ./yamls\n",
        encoding="utf-8",
    )

    settings = load_launch_settings(str(settings_file))

    assert settings["default_yaml"] == (tmp_path / "configs" / "main.yaml").resolve()
    assert settings["browse_dir"] == (tmp_path / "yamls").resolve()


def test_load_launch_settings_without_file_returns_defaults():
    settings = load_launch_settings(None)

    assert settings["default_yaml"] is None
    assert settings["browse_dir"] is None


def test_help_content_contains_examples_and_faq():
    assert "FAQ" in HELP_CONTENT
    assert "Минимальный пример" in HELP_CONTENT
    assert "pipeline" in HELP_CONTENT


def test_load_ui_state_returns_empty_dict_for_missing_file(tmp_path):
    state_path = tmp_path / "missing-state.json"

    assert load_ui_state(state_path) == {}


def test_save_and_load_ui_state_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    state = {"/path/to/config.yaml": {"convert": {"bitrate": 192, "output": "/tmp"}}}

    save_ui_state(state, state_path)

    assert load_ui_state(state_path) == state


def test_load_ui_state_ignores_invalid_json(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{broken", encoding="utf-8")

    assert load_ui_state(state_path) == {}


class _EntryWidget:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _TextWidget:
    def __init__(self, value):
        self.value = value

    def get(self, *_args):
        return self.value


class _BoolVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _BoolWidget:
    def __init__(self, value):
        self.var = _BoolVar(value)


class _MultiChoiceWidget:
    def __init__(self, options, selected_indexes):
        self.options = options
        self.selected_indexes = selected_indexes

    def curselection(self):
        return self.selected_indexes

    def get(self, index):
        return self.options[index]


class _SliderWidget:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _DummyApp:
    def __init__(self, engine):
        self.engine = engine
        self.after_calls = []
        self.logged = []

    def _append_run_log(self, run_id, msg):
        self.logged.append((run_id, msg))

    def _finish_run(self, *args):
        return None

    def after(self, _delay, callback, *args):
        self.after_calls.append((callback, args))


def test_collect_form_parses_supported_widget_types(monkeypatch):
    monkeypatch.setenv("TOKEN_ENV", "token-from-env")
    fields = {
        "title": ({"type": "string", "required": True}, _EntryWidget(" hello ")),
        "count": ({"type": "int"}, _EntryWidget("7")),
        "ratio": ({"type": "float"}, _EntryWidget("0.75")),
        "notes": ({"type": "text"}, _TextWidget("line1\n")),
        "enabled": ({"type": "bool"}, _BoolWidget(True)),
        "mode": ({"type": "tri_bool"}, _EntryWidget("false")),
        "tags": (
            {"type": "multichoice"},
            _MultiChoiceWidget(["a", "b", "c"], [0, 2]),
        ),
        "slider": (
            {"type": "float"},
            {"kind": "slider", "scale": 100, "control": _SliderWidget(35)},
        ),
        "token": ({"type": "secret", "source": "env", "env": "TOKEN_ENV"}, _EntryWidget("ignored")),
        "pairs": ({"type": "kv_list"}, _TextWidget("- k: v")),
    }

    data = App._collect_form(object(), fields)

    assert data == {
        "title": "hello",
        "count": 7,
        "ratio": 0.75,
        "notes": "line1",
        "enabled": True,
        "mode": "false",
        "tags": ["a", "c"],
        "slider": 0.35,
        "token": "token-from-env",
        "pairs": [{"k": "v"}],
    }


def test_collect_form_reports_required_and_path_errors(tmp_path):
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("x", encoding="utf-8")
    fields = {
        "required_name": ({"type": "string", "required": True}, _EntryWidget("")),
        "dir_path": (
            {"type": "path", "must_exist": True, "kind": "dir"},
            _EntryWidget(str(file_path)),
        ),
        "list_field": ({"type": "kv_list"}, _TextWidget("{}")),
    }

    with pytest.raises(EngineError) as exc:
        App._collect_form(object(), fields)

    message = str(exc.value)
    assert "required_name is required" in message
    assert "dir_path must be a directory" in message
    assert "list_field must be a list" in message


def test_slider_entry_commit_syncs_fallback_and_scaled_value():
    sync_calls = []
    slider = _SliderWidget(12)
    value_var = _EntryWidget("bad-number")
    state = {"syncing": False}

    App._on_slider_entry_commit(
        state=state,
        value_var=value_var,
        sync=sync_calls.append,
        slider=slider,
        scale=10,
    )

    value_var.value = "1.9"
    App._on_slider_entry_commit(
        state=state,
        value_var=value_var,
        sync=sync_calls.append,
        slider=slider,
        scale=10,
    )

    assert sync_calls == [12, 19]


def test_run_action_worker_schedules_success_and_failures():
    class _Engine:
        def __init__(self, outcome):
            self.outcome = outcome

        def run_action(self, action_id, form, logger):
            logger(f"running {action_id} with {form}")
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    success_app = _DummyApp(_Engine({"ok": True}))
    App._run_action_worker(success_app, 1, "build", {"x": 1})
    assert len(success_app.after_calls) == 2
    assert success_app.after_calls[0][0] == success_app._append_run_log
    assert success_app.after_calls[1][0] == success_app._finish_run
    assert success_app.after_calls[1][1] == (1, True, {"ok": True}, None, False)

    cancelled_app = _DummyApp(_Engine(ActionCancelledError("stop")))
    App._run_action_worker(cancelled_app, 2, "build", {})
    assert cancelled_app.after_calls[-1][1] == (2, False, None, "stop", True)

    failed_app = _DummyApp(_Engine(ValueError("boom")))
    App._run_action_worker(failed_app, 3, "build", {})
    assert failed_app.after_calls[-1][1] == (3, False, None, "boom", False)


def test_has_editable_fields_ignores_env_secrets():
    assert App._has_editable_fields(object(), {"fields": "not-a-list"}) is False
    assert (
        App._has_editable_fields(
            object(),
            {
                "fields": [
                    {"type": "secret", "source": "env"},
                    "skip-me",
                ]
            },
        )
        is False
    )
    assert (
        App._has_editable_fields(
            object(),
            {
                "fields": [
                    {"type": "secret", "source": "env"},
                    {"type": "string"},
                ]
            },
        )
        is True
    )
