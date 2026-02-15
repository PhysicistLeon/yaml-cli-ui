import io

from yaml_cli_ui.engine import PipelineEngine, SafeEvaluator, render_template, to_dotdict


def test_template_eval():
    ev = SafeEvaluator({"form": {"x": 3}, "len": len, "empty": lambda x: x in (None, ""), "exists": lambda _: True})
    assert render_template("${form['x']}", ev) == 3


def test_argv_serialization_modes():
    engine = PipelineEngine({"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}})
    ev = SafeEvaluator(
        {
            "form": to_dotdict({"flag": True, "items": ["ru", "en"], "tri": "false", "name": "abc"}),
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
            {"opt": "--switch", "from": "${form.tri}", "mode": "flag", "false_opt": "--no-switch"},
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
    engine = PipelineEngine({"version": 1, "actions": {"a": {"title": "A", "run": {"program": "x"}}}})
    stream = io.StringIO("10%\r20%\rdone\n")
    captured = []
    logs = []

    engine._stream_output("stderr", stream, captured, logs.append)

    assert captured == ["10%", "20%", "done"]
    assert logs == ["[stderr] 10%", "[stderr] 20%", "[stderr] done"]




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
