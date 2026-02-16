# pylint: disable=protected-access
import io
import sys
import threading
import time

from yaml_cli_ui.engine import (
    ActionCancelledError,
    PipelineEngine,
    SafeEvaluator,
    render_template,
    to_dotdict,
)


def test_template_eval():
    ev = SafeEvaluator(
        {
            "form": {"x": 3},
            "len": len,
            "empty": lambda x: x in (None, ""),
            "exists": lambda _: True,
        }
    )
    assert render_template("${form['x']}", ev) == 3


def test_argv_serialization_modes():
    engine = PipelineEngine(
        {"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}}
    )
    ev = SafeEvaluator(
        {
            "form": to_dotdict(
                {"flag": True, "items": ["ru", "en"], "tri": "false", "name": "abc"}
            ),
            "vars": {},
            "env": {},
            "step": {},
            "cwd": ".",
            "home": ".",
            "temp": ".",
            "os": "nt",
            "len": len,
            "empty": lambda x: x in (None, "") or x == [],
            "exists": lambda _: True,
        }
    )
    argv = engine.serialize_argv(
        [
            "literal value",
            {"--flag": "${form.flag}"},
            {"--name": "${form.name}"},
            {"opt": "--langs", "from": "${form.items}", "mode": "join", "joiner": ","},
            {
                "opt": "--switch",
                "from": "${form.tri}",
                "mode": "flag",
                "false_opt": "--no-switch",
            },
        ],
        ev,
    )
    assert argv == [
        "literal value",
        "--flag",
        "--name",
        "abc",
        "--langs",
        "ru,en",
        "--no-switch",
    ]


def test_stream_output_handles_carriage_return_progress():
    engine = PipelineEngine(
        {"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}}
    )
    stream = io.StringIO("10%\r20%\rdone\n")
    captured = []
    logs = []

    engine._stream_output("stderr", stream, captured, logs.append)

    assert captured == ["10%", "20%", "done"]
    assert logs == ["[stderr] 10%", "[stderr] 20%", "[stderr] done"]


def test_python_program_detection():
    engine = PipelineEngine(
        {"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}}
    )

    assert engine._looks_like_python_program("python")
    assert engine._looks_like_python_program("python.exe")
    assert engine._looks_like_python_program(r"C:/venv/Scripts/python.exe")
    assert engine._looks_like_python_program("python3")
    assert not engine._looks_like_python_program("py")
    assert not engine._looks_like_python_program("node")


def test_sanitize_child_env_for_embedded_tk():
    engine = PipelineEngine(
        {"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}}
    )
    env = {
        "PATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345;C:\Windows\System32",
        "TCL_LIBRARY": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tcl_data",
        "TK_LIBRARY": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tk_data",
        "PYTHONHOME": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345",
        "PYTHONPATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345",
        "TCLLIBPATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tcl_data",
        "SYSTEMROOT": r"C:\Windows",
    }

    sanitized = engine._sanitize_child_env_for_embedded_tk(env)

    assert "TCL_LIBRARY" not in sanitized
    assert "TK_LIBRARY" not in sanitized
    assert "PYTHONHOME" not in sanitized
    assert "PYTHONPATH" not in sanitized
    assert "TCLLIBPATH" not in sanitized
    assert "PATH" not in sanitized
    assert sanitized["SYSTEMROOT"] == r"C:\Windows"


def test_python_runtime_override_program_resolution():
    engine = PipelineEngine(
        {
            "version": 1,
            "runtime": {"python": {"executable": "C:/venv/python.exe"}},
            "actions": {"a": {"title": "A", "run": {"program": "python"}}},
        }
    )
    ev = SafeEvaluator(
        {
            "form": {},
            "vars": {},
            "env": {},
            "step": {},
            "cwd": ".",
            "home": ".",
            "temp": ".",
            "os": "nt",
            "len": len,
            "empty": lambda x: x in (None, "") or x == [],
            "exists": lambda _: True,
        }
    )

    assert engine._resolve_program("python", ev) == "C:/venv/python.exe"
    assert engine._resolve_program("python3", ev) == "python3"


def test_stop_action_cancels_running_process():
    engine = PipelineEngine(
        {
            "version": 1,
            "actions": {
                "slow": {
                    "title": "Slow",
                    "run": {
                        "program": "python",
                        "argv": ["-c", "import time; time.sleep(5)"],
                    },
                }
            },
        }
    )

    errors = []

    def _runner() -> None:
        try:
            engine.run_action("slow", {}, lambda _msg: None)
        except ActionCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    time.sleep(0.3)
    engine.stop_action("slow")
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert errors
    assert isinstance(errors[0], ActionCancelledError)


def test_stop_action_cancels_process_group_and_returns_quickly():
    script = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)']); "
        "time.sleep(5)"
    )
    engine = PipelineEngine(
        {
            "version": 1,
            "actions": {
                "slow": {
                    "title": "Slow",
                    "run": {
                        "program": sys.executable,
                        "argv": ["-c", script],
                    },
                }
            },
        }
    )

    errors = []

    def _runner() -> None:
        try:
            engine.run_action("slow", {}, lambda _msg: None)
        except ActionCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=_runner, daemon=True)
    started = time.perf_counter()
    worker.start()
    time.sleep(0.3)
    engine.stop_action("slow")
    worker.join(timeout=2)
    elapsed = time.perf_counter() - started

    assert not worker.is_alive()
    assert errors
    assert isinstance(errors[0], ActionCancelledError)
    assert elapsed < 2
