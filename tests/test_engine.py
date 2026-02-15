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
