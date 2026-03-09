# pylint: disable=import-error,protected-access,redefined-outer-name

import sys
import time
import tkinter as tk

import pytest

from yaml_cli_ui.app_v2 import (
    AppV2,
    launcher_param_plan,
    resolve_profile_ui_state,
    run_launcher,
)
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.models import (
    LauncherDef,
    ParamDef,
    ParamType,
    ProfileDef,
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
        },
        launchers={
            "l": LauncherDef(title="L", use="c", with_values={"y": "fixed"}),
        },
    )

    editable, fixed = launcher_param_plan(doc, "l")

    assert set(editable.keys()) == {"x"}
    assert fixed == {"y": "fixed"}


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


def test_start_launcher_autorun_when_all_editable_ready(tmp_path, monkeypatch):
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
        app.start_launcher("l")
        assert calls == [{"name": "l", "values": {}}]
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
