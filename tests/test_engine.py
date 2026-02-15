from yaml_cli_ui.engine import WorkflowEngine


def test_extended_arg_serialization_and_step_results():
    cfg = {
        "version": 1,
        "actions": {
            "a": {
                "title": "A",
                "pipeline": [
                    {
                        "id": "r1",
                        "run": {
                            "program": "python",
                            "argv": [
                                "-c",
                                "import sys;print('ok')",
                                {"--flag": True},
                                {
                                    "opt": "--items",
                                    "from": ["x", "y"],
                                    "mode": "join",
                                    "joiner": ",",
                                },
                            ],
                            "capture": True,
                        },
                    }
                ],
            }
        },
    }
    engine = WorkflowEngine(cfg)
    cmds, results = engine.run_action("a", {})
    assert cmds[0][1][0:2] == ["python", "-c"]
    assert "--flag" in cmds[0][1]
    assert "--items" in cmds[0][1]
    assert results["r1"].exit_code == 0


def test_foreach_pipeline():
    cfg = {
        "version": 1,
        "actions": {
            "b": {
                "title": "B",
                "pipeline": [
                    {
                        "id": "loop",
                        "foreach": {
                            "in": "${form.items}",
                            "as": "job",
                            "steps": [
                                {
                                    "id": "echo",
                                    "run": {
                                        "program": "python",
                                        "argv": ["-c", "import sys; print(sys.argv[1])", "${job.v}"],
                                        "capture": True,
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        },
    }
    engine = WorkflowEngine(cfg)
    cmds, results = engine.run_action("b", {"items": [{"v": "1"}, {"v": "2"}]})
    assert len(cmds) == 2
    assert results["echo"].stdout.strip() in {"1", "2"}
