import sys
import time
import tkinter as tk

import pytest

from yaml_cli_ui.app_v2 import AppV2, run_launcher
from yaml_cli_ui.v2.loader import load_v2_document


@pytest.fixture()
def v2_yaml(tmp_path):
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
        assert app.status_labels["run_hello"].cget("text") == "success"
    finally:
        app.destroy()
