# pylint: disable=import-error,protected-access,redefined-outer-name

import sys
import time
import tkinter as tk
from tkinter import ttk

import pytest

from yaml_cli_ui.app_v2 import (
    AppV2,
    collect_used_params_for_launcher,
    launcher_param_plan,
    resolve_profile_ui_state,
    materialize_launcher_params,
    run_launcher,
    should_open_launcher_dialog,
)
from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.persistence import save_v2_presets, save_v2_state
from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    LauncherDef,
    PipelineDef,
    ParamDef,
    ParamType,
    ProfileDef,
    SecretSource,
    RunSpec,
    StepSpec,
    V2Document,
)


@pytest.fixture(name="v2_yaml")
def fixture_v2_yaml(tmp_path):
    path = tmp_path / "ui_v2.yaml"
    path.write_text(
        f"""
version: 2
profiles:
  fast: {{}}
  safe: {{}}
params:
  name:
    type: string
    required: true
  mode:
    type: choice
    options: [quick, full]
    default: quick
  token:
    type: secret
    default: top-secret
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  run_hello:
    title: Run hello
    info: test launcher
    use: hello
    with:
      mode: full
""",
        encoding="utf-8",
    )
    return path


def _maybe_app(path):
    try:
        app = AppV2(str(path))
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    app.withdraw()
    return app


def test_resolve_profile_ui_state():
    doc_none = V2Document(profiles={})
    assert resolve_profile_ui_state(doc_none) == (False, None, [])

    doc_one = V2Document(profiles={"only": ProfileDef()})
    assert resolve_profile_ui_state(doc_one) == (False, "only", ["only"])

    doc_many = V2Document(profiles={"a": ProfileDef(), "b": ProfileDef()})
    show, selected, names = resolve_profile_ui_state(doc_many)
    assert show is True
    assert selected == "a"
    assert names == ["a", "b"]


def test_launcher_param_plan_with_fixed_bindings():
    doc = V2Document(
        params={
            "x": ParamDef(type=ParamType.STRING),
            "y": ParamDef(type=ParamType.STRING),
            "unused": ParamDef(type=ParamType.STRING),
        },
        commands={
            "c": CommandDef(run=RunSpec(program="echo", argv=["$params.x", "$params.y"]))
        },
        launchers={
            "l": LauncherDef(title="L", use="c", with_values={"y": "fixed"}),
        },
    )

    editable, fixed = launcher_param_plan(doc, "l")

    assert set(editable.keys()) == {"x"}
    assert fixed == {"y": "fixed"}


def test_launcher_param_plan_with_no_used_params():
    doc = V2Document(
        params={
            "x": ParamDef(type=ParamType.STRING),
        },
        commands={
            "c": CommandDef(run=RunSpec(program="echo", argv=["ok"]))
        },
        launchers={
            "l": LauncherDef(title="L", use="c", with_values={"x": "fixed"}),
        },
    )

    editable, fixed = launcher_param_plan(doc, "l")

    assert editable == {}
    assert fixed == {}


def test_should_open_launcher_dialog_no_params_is_false():
    assert should_open_launcher_dialog({}, {}) is False


def test_should_open_launcher_dialog_with_defaulted_editable_is_true():
    assert should_open_launcher_dialog({"username": ParamDef(type=ParamType.STRING, default="Leon")}, {}) is True


def test_should_open_launcher_dialog_with_only_fixed_with_values_is_true():
    assert should_open_launcher_dialog({}, {"username": "fixed"}) is True


def test_collect_used_params_for_command_filters_unused():
    doc = V2Document(
        params={
            "source_url": ParamDef(type=ParamType.STRING),
            "bitrate": ParamDef(type=ParamType.STRING),
            "unused_param": ParamDef(type=ParamType.STRING),
        },
        commands={
            "download": CommandDef(run=RunSpec(program="yt", argv=["$params.source_url"]))
        },
        launchers={"run": LauncherDef(title="Run", use="download")},
    )

    used = collect_used_params_for_launcher(doc, "run")
    assert used == {"source_url"}


def test_collect_used_params_for_pipeline_nested_graph():
    doc = V2Document(
        params={
            "source_url": ParamDef(type=ParamType.STRING),
            "collection": ParamDef(type=ParamType.STRING),
            "unused_param": ParamDef(type=ParamType.STRING),
        },
        commands={
            "fetch": CommandDef(run=RunSpec(program="fetch", argv=["$params.source_url"])),
            "save": CommandDef(run=RunSpec(program="save", argv=["$params.collection"])),
        },
        pipelines={
            "main": PipelineDef(
                steps=[
                    "fetch",
                    StepSpec(
                        foreach=ForeachSpec(
                            in_expr="$params.collection",
                            as_name="item",
                            steps=["save"],
                        )
                    ),
                ]
            )
        },
        launchers={"run": LauncherDef(title="Run", use="main")},
    )

    used = collect_used_params_for_launcher(doc, "run")
    assert used == {"source_url", "collection"}




def test_materialize_launcher_params_precedence():
    doc = V2Document(
        params={"username": ParamDef(type=ParamType.STRING, default="Leon")},
        commands={"hello": CommandDef(run=RunSpec(program="echo", argv=["$params.username"]))},
        launchers={"l": LauncherDef(title="L", use="hello", with_values={"username": "Dave"})},
    )

    merged = materialize_launcher_params(
        doc,
        "l",
        state_values={"username": "Alice", "unknown": "state"},
        preset_values={"username": "Bob", "unknown": "preset"},
        user_values={"username": "Carol", "unknown": "user"},
    )

    assert merged["username"] == "Dave"
    assert "unknown" not in merged




def test_default_materialization_does_not_resolve_secret_sources():
    doc = V2Document(
        params={
            "plain": ParamDef(type=ParamType.STRING, default="Leon"),
            "env_secret": ParamDef(type=ParamType.SECRET, source=SecretSource.ENV, env="APP_SECRET"),
            "vault_secret": ParamDef(type=ParamType.SECRET, source=SecretSource.VAULT),
            "explicit_secret_default": ParamDef(type=ParamType.SECRET, default="keep-me"),
        },
        commands={"hello": CommandDef(run=RunSpec(program="echo", argv=["ok"]))},
        launchers={"l": LauncherDef(title="L", use="hello")},
    )

    merged = materialize_launcher_params(doc, "l")

    assert merged == {"plain": "Leon", "explicit_secret_default": "keep-me"}
def test_run_launcher_materializes_root_default_without_with(tmp_path):
    path = tmp_path / "default_param.yaml"
    path.write_text(
        f"""
version: 2
params:
  username:
    type: string
    default: Leon
commands:
  hello_username:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('hello from v2 to ${{params.username}}')"]
launchers:
  hello2:
    title: Hello with name
    use: hello_username
""",
        encoding="utf-8",
    )

    doc = load_v2_document(path)
    result = run_launcher(doc, "hello2", {})

    assert result.status.value == "success"
    assert "hello from v2 to Leon" in (result.stdout or "")


def test_run_launcher_missing_required_param_without_default_fails(tmp_path):
    path = tmp_path / "required_param.yaml"
    path.write_text(
        f"""
version: 2
params:
  username:
    type: string
    required: true
commands:
  hello_username:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('hello from v2 to ${{params.username}}')"]
launchers:
  hello2:
    title: Hello with name
    use: hello_username
""",
        encoding="utf-8",
    )

    doc = load_v2_document(path)
    with pytest.raises(V2ExpressionError, match="username"):
        run_launcher(doc, "hello2", {})
def test_run_launcher_executes(v2_yaml):
    doc = load_v2_document(v2_yaml)

    result = run_launcher(doc, "run_hello", {"name": "Alice"}, selected_profile_name="fast")

    assert result.status.value == "success"
    assert "ok" in (result.stdout or "")


def test_app_v2_renders_launchers_and_profiles(v2_yaml):
    app = _maybe_app(v2_yaml)
    try:
        assert "run_hello" in app.launcher_buttons
        assert app.profile_combo is not None
        assert app.profile_var.get() in {"fast", "safe"}
    finally:
        app.destroy()


def test_background_completion_updates_history_and_logs(v2_yaml):
    app = _maybe_app(v2_yaml)
    try:
        start = time.time()
        app._execute_in_background("run_hello", {"name": "A"})
        assert (time.time() - start) < 0.5

        for _ in range(100):
            app.update()
            if app.history.records and list(app.history.records.values())[-1].status != "running":
                break
            time.sleep(0.02)

        rec = list(app.history.records.values())[-1]
        assert rec.status == "success"
        assert "run_hello" in app.log_widgets["__all__"].get("1.0", "end")
        assert "success" in app.status_labels["run_hello"].cget("text")
    finally:
        app.destroy()


def test_start_launcher_opens_dialog_when_params_are_defaulted(tmp_path, monkeypatch):
    path = tmp_path / "auto.yaml"
    path.write_text(
        f"""
version: 2
params:
  env_secret:
    type: secret
    required: true
    source: env
    env: MY_ENV_SECRET
  d:
    type: string
    default: hello
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MY_ENV_SECRET", "s3cr3t")
    app = _maybe_app(path)
    try:
        calls: list[dict[str, str]] = []

        def fake_exec(name, values):
            calls.append({"name": name, "values": values})

        app._execute_in_background = fake_exec  # type: ignore[method-assign]
        created = {"count": 0}

        real_toplevel = tk.Toplevel

        def capture_toplevel(*args, **kwargs):
            created["count"] += 1
            return real_toplevel(*args, **kwargs)

        monkeypatch.setattr("yaml_cli_ui.app_v2.tk.Toplevel", capture_toplevel)
        app.start_launcher("l")
        assert calls == []
        assert created["count"] == 1
    finally:
        app.destroy()


def test_start_launcher_opens_dialog_when_param_prefilled_from_state_or_preset(tmp_path, monkeypatch):
    path = tmp_path / "prefilled.yaml"
    path.write_text(
        f"""
version: 2
params:
  username:
    type: string
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')", "$params.username"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    save_v2_state(
        path,
        {
            "version": 2,
            "selected_profile": None,
            "launchers": {"l": {"last_values": {"username": "state_user"}, "last_selected_preset": "p"}},
        },
    )
    save_v2_presets(
        path,
        {"version": 2, "launchers": {"l": {"presets": {"p": {"params": {"username": "preset_user"}}}}}},
    )

    app = _maybe_app(path)
    try:
        calls: list[dict[str, str]] = []

        def fake_exec(name, values):
            calls.append({"name": name, "values": values})

        app._execute_in_background = fake_exec  # type: ignore[method-assign]
        created = {"count": 0}

        real_toplevel = tk.Toplevel

        def capture_toplevel(*args, **kwargs):
            created["count"] += 1
            return real_toplevel(*args, **kwargs)

        monkeypatch.setattr("yaml_cli_ui.app_v2.tk.Toplevel", capture_toplevel)
        app.start_launcher("l")
        assert calls == []
        assert created["count"] == 1
    finally:
        app.destroy()


def test_start_launcher_opens_dialog_when_only_fixed_used_params(tmp_path, monkeypatch):
    path = tmp_path / "fixed_only.yaml"
    path.write_text(
        f"""
version: 2
params:
  collection:
    type: string
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')", "$params.collection"]
launchers:
  l:
    title: L
    use: hello
    with:
      collection: fixed
""",
        encoding="utf-8",
    )

    captured = {}

    def fake_create(_parent, _params, *, initial_values=None, fixed_values=None):
        captured["initial_values"] = dict(initial_values or {})
        captured["fixed_values"] = dict(fixed_values or {})
        return {}

    monkeypatch.setattr("yaml_cli_ui.app_v2.create_v2_form_fields", fake_create)

    app = _maybe_app(path)
    try:
        calls: list[dict[str, str]] = []

        def fake_exec(name, values):
            calls.append({"name": name, "values": values})

        app._execute_in_background = fake_exec  # type: ignore[method-assign]
        created = {"count": 0}

        real_toplevel = tk.Toplevel

        def capture_toplevel(*args, **kwargs):
            created["count"] += 1
            return real_toplevel(*args, **kwargs)

        monkeypatch.setattr("yaml_cli_ui.app_v2.tk.Toplevel", capture_toplevel)
        app.start_launcher("l")

        assert calls == []
        assert created["count"] == 1
        assert captured["fixed_values"] == {"collection": "fixed"}
        assert captured["initial_values"] == {}
    finally:
        app.destroy()


def test_start_launcher_skips_dialog_when_launcher_has_no_params(tmp_path):
    path = tmp_path / "no_params.yaml"
    path.write_text(
        f"""
version: 2
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    app = _maybe_app(path)
    try:
        calls: list[dict[str, str]] = []

        def fake_exec(name, values):
            calls.append({"name": name, "values": values})

        app._execute_in_background = fake_exec  # type: ignore[method-assign]
        app.start_launcher("l")
        assert calls == [{"name": "l", "values": {}}]
    finally:
        app.destroy()


def test_start_launcher_opens_dialog_when_editable_exists(tmp_path, monkeypatch):
    path = tmp_path / "needs_input.yaml"
    path.write_text(
        f"""
version: 2
params:
  source_url:
    type: string
    required: true
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')", "$params.source_url"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    app = _maybe_app(path)
    try:
        created = {"count": 0}

        real_toplevel = tk.Toplevel

        def capture_toplevel(*args, **kwargs):
            created["count"] += 1
            return real_toplevel(*args, **kwargs)

        monkeypatch.setattr("yaml_cli_ui.app_v2.tk.Toplevel", capture_toplevel)
        app.start_launcher("l")
        assert created["count"] == 1
    finally:
        app.destroy()


def test_launcher_info_attaches_tooltip_not_inline_label(v2_yaml):
    app = _maybe_app(v2_yaml)
    try:
        btn = app.launcher_buttons["run_hello"]
        assert btn.bind("<Enter>")
        labels = [child for child in btn.master.winfo_children() if isinstance(child, ttk.Label)]
        assert labels == []
    finally:
        app.destroy()


def test_reload_does_not_duplicate_launcher_tabs(v2_yaml):
    app = _maybe_app(v2_yaml)
    try:
        app.reload()
        app.reload()
        tab_count = len(app.output_notebook.tabs())
        assert tab_count == 2  # All runs + run_hello
    finally:
        app.destroy()


def test_reload_falls_back_when_saved_profile_missing(tmp_path):
    path = tmp_path / "missing_profile.yaml"
    path.write_text(
        f"""
version: 2
profiles:
  fast: {{}}
  safe: {{}}
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    save_v2_state(path, {"version": 2, "selected_profile": "gone", "launchers": {}})

    app = _maybe_app(path)
    try:
        assert app.profile_var.get() == "fast"
        assert app.profile_combo is not None
    finally:
        app.destroy()


def test_start_launcher_form_receives_prefilled_and_fixed_values(tmp_path, monkeypatch):
    path = tmp_path / "prefilled_and_fixed.yaml"
    path.write_text(
        f"""
version: 2
params:
  username:
    type: string
  collection:
    type: string
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')", "$params.username", "$params.collection"]
launchers:
  l:
    title: L
    use: hello
    with:
      collection: fixed_collection
""",
        encoding="utf-8",
    )
    save_v2_state(
        path,
        {
            "version": 2,
            "selected_profile": None,
            "launchers": {"l": {"last_values": {"username": "state_user"}, "last_selected_preset": "p"}},
        },
    )
    save_v2_presets(
        path,
        {"version": 2, "launchers": {"l": {"presets": {"p": {"params": {"username": "preset_user"}}}}}},
    )

    captured = {}

    def fake_create(_parent, _params, *, initial_values=None, fixed_values=None):
        captured["initial_values"] = dict(initial_values or {})
        captured["fixed_values"] = dict(fixed_values or {})
        return {}

    monkeypatch.setattr("yaml_cli_ui.app_v2.create_v2_form_fields", fake_create)

    app = _maybe_app(path)
    try:
        calls: list[dict[str, str]] = []

        def fake_exec(name, values):
            calls.append({"name": name, "values": values})

        app._execute_in_background = fake_exec  # type: ignore[method-assign]
        created = {"count": 0}

        real_toplevel = tk.Toplevel

        def capture_toplevel(*args, **kwargs):
            created["count"] += 1
            return real_toplevel(*args, **kwargs)

        monkeypatch.setattr("yaml_cli_ui.app_v2.tk.Toplevel", capture_toplevel)
        app.start_launcher("l")

        assert calls == []
        assert created["count"] == 1
        assert captured["initial_values"]["username"] == "preset_user"
        assert captured["fixed_values"] == {"collection": "fixed_collection"}
    finally:
        app.destroy()


def test_launcher_dialog_prefill_precedence_defaults_state_preset_with(tmp_path, monkeypatch):
    path = tmp_path / "precedence.yaml"
    path.write_text(
        f"""
version: 2
profiles:
  p1: {{}}
params:
  a:
    type: string
    default: dflt_a
  b:
    type: string
    default: dflt_b
  c:
    type: string
    default: dflt_c
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: hello
    with:
      c: fixed_c
""",
        encoding="utf-8",
    )
    save_v2_state(
        path,
        {
            "version": 2,
            "selected_profile": "p1",
            "launchers": {"l": {"last_values": {"a": "state_a", "c": "state_c"}}},
        },
    )
    save_v2_presets(
        path,
        {
            "version": 2,
            "launchers": {
                "l": {
                    "presets": {
                        "p": {"params": {"a": "preset_a", "b": "preset_b", "c": "preset_c"}}
                    }
                }
            },
        },
    )

    captured = {}

    def fake_create(_parent, _params, *, initial_values=None, fixed_values=None):
        captured["initial_values"] = dict(initial_values or {})
        captured["fixed_values"] = dict(fixed_values or {})
        return {}

    monkeypatch.setattr("yaml_cli_ui.app_v2.create_v2_form_fields", fake_create)

    app = _maybe_app(path)
    try:
        app.persistence.set_last_selected_preset("l", "p")
        app.start_launcher("l")
    finally:
        app.destroy()

    assert captured["initial_values"]["a"] == "preset_a"
    assert captured["initial_values"]["b"] == "preset_b"
    assert captured["initial_values"].get("c") is None
    assert captured["fixed_values"]["c"] == "fixed_c"


def test_reload_shows_aggregated_persistence_warning(tmp_path, monkeypatch):
    path = tmp_path / "warn.yaml"
    path.write_text(
        f"""
version: 2
profiles:
  p1: {{}}
commands:
  hello:
    run:
      program: "{sys.executable}"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: hello
""",
        encoding="utf-8",
    )
    # both files malformed to produce two warnings
    (tmp_path / "warn.yaml.launchers.presets.json").write_text("{oops", encoding="utf-8")
    (tmp_path / "warn.yaml.state.json").write_text("{oops", encoding="utf-8")

    calls = []

    def fake_showwarning(title, message, _parent=None):
        calls.append((title, message))

    monkeypatch.setattr("yaml_cli_ui.app_v2.messagebox.showwarning", fake_showwarning)

    app = _maybe_app(path)
    try:
        assert len(calls) == 1
        assert "Using safe defaults" in calls[0][1]
    finally:
        app.destroy()
