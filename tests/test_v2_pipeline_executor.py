# pylint: disable=import-error

from __future__ import annotations

import sys

import pytest

from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.executor import execute_command_def, execute_pipeline_def
from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    OnErrorSpec,
    PipelineDef,
    RunSpec,
    StepSpec,
    StepStatus,
    V2Document,
)


def _cmd_ok(msg: str = "ok") -> CommandDef:
    return CommandDef(run=RunSpec(program=sys.executable, argv=["-c", f"print('{msg}')"]))


def _cmd_fail(code: int = 3) -> CommandDef:
    return CommandDef(run=RunSpec(program=sys.executable, argv=["-c", f"import sys; sys.exit({code})"]))


def _ctx(params: dict | None = None) -> dict:
    return {
        "params": params or {},
        "locals": {},
        "profile": {},
        "run": {},
        "steps": {},
    }


def test_simple_pipeline_success():
    doc = V2Document(
        commands={"a": _cmd_ok("a"), "b": _cmd_ok("b")},
        pipelines={"main": PipelineDef(steps=["a", "b"])},
    )
    result = execute_pipeline_def(doc.pipelines["main"], doc=doc, context=_ctx())

    assert result.status == StepStatus.SUCCESS
    assert list(result.children.keys()) == ["a", "b"]


def test_nested_pipeline():
    doc = V2Document(
        commands={"leaf": _cmd_ok("leaf")},
        pipelines={"inner": PipelineDef(steps=["leaf"]), "outer": PipelineDef(steps=["inner"])},
    )
    result = execute_pipeline_def(doc.pipelines["outer"], doc=doc, context=_ctx())

    assert result.status == StepStatus.SUCCESS
    assert "inner" in result.children
    assert "leaf" in result.children["inner"].children


def test_short_step_syntax_name_dedup():
    doc = V2Document(commands={"hello": _cmd_ok("x")}, pipelines={"p": PipelineDef(steps=["hello", "hello"])})
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx())

    assert list(result.children.keys()) == ["hello", "hello_2"]


def test_expanded_with_overrides_short_binding():
    doc = V2Document(
        commands={
            "show": CommandDef(
                run=RunSpec(
                    program=sys.executable,
                    argv=["-c", "import sys; print(sys.argv[1], sys.argv[2])", "$collection", "$params.collection"],
                )
            )
        },
        pipelines={
            "p": PipelineDef(
                steps=[StepSpec(step="s", use="show", with_values={"collection": "from_with"})]
            )
        },
    )
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx({"collection": "from_params"}))

    assert result.status == StepStatus.SUCCESS
    assert "from_with from_params" in (result.children["s"].stdout or "")


def test_step_when_false_skipped_and_pipeline_continues():
    doc = V2Document(
        commands={"a": _cmd_ok(), "b": _cmd_ok()},
        pipelines={"p": PipelineDef(steps=[StepSpec(step="skip", when="${false}", use="a"), "b"])},
    )
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx())

    assert result.children["skip"].status == StepStatus.SKIPPED
    assert result.children["b"].status == StepStatus.SUCCESS


def test_failure_stops_pipeline_without_continue_on_error():
    doc = V2Document(commands={"bad": _cmd_fail(), "later": _cmd_ok()}, pipelines={"p": PipelineDef(steps=["bad", "later"])})
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx())

    assert result.status == StepStatus.FAILED
    assert "later" not in result.children


def test_step_continue_on_error_true_continues_but_pipeline_failed():
    doc = V2Document(
        commands={"bad": _cmd_fail(), "later": _cmd_ok()},
        pipelines={"p": PipelineDef(steps=[StepSpec(use="bad", continue_on_error=True), "later"])},
    )
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx())

    assert result.status == StepStatus.FAILED
    assert result.children["later"].status == StepStatus.SUCCESS


def test_foreach_success_meta_and_iterations():
    doc = V2Document(
        commands={"work": _cmd_ok("iter")},
        pipelines={
            "p": PipelineDef(
                steps=[
                    StepSpec(
                        step="per_job",
                        foreach=ForeachSpec(
                            in_expr="$params.jobs",
                            as_name="job",
                            steps=["work"],
                        ),
                    )
                ]
            )
        },
    )
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx({"jobs": [{"n": 1}, {"n": 2}]}))
    foreach_result = result.children["per_job"]

    assert foreach_result.meta["iteration_count"] == 2
    assert "iter_0" in foreach_result.children and "iter_1" in foreach_result.children


def test_foreach_loop_vars():
    doc = V2Document(
        commands={
            "loop_echo": CommandDef(
                run=RunSpec(
                    program=sys.executable,
                    argv=[
                        "-c",
                        "import sys; print(sys.argv[1], sys.argv[2], sys.argv[3])",
                        "$loop.index",
                        "$loop.first",
                        "$loop.last",
                    ],
                )
            )
        },
        pipelines={
            "p": PipelineDef(
                steps=[StepSpec(step="f", foreach=ForeachSpec(in_expr="$params.jobs", as_name="job", steps=["loop_echo"]))]
            )
        },
    )
    result = execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx({"jobs": [1, 2]}))
    out0 = result.children["f"].children["iter_0"].children["loop_echo"].stdout or ""
    out1 = result.children["f"].children["iter_1"].children["loop_echo"].stdout or ""

    assert "0 True False" in out0
    assert "1 False True" in out1


def test_foreach_invalid_input_raises():
    doc = V2Document(
        commands={"x": _cmd_ok()},
        pipelines={"p": PipelineDef(steps=[StepSpec(foreach=ForeachSpec(in_expr="$params.jobs", as_name="job", steps=["x"]))])},
    )
    with pytest.raises(V2ExecutionError, match="foreach.in"):
        execute_pipeline_def(doc.pipelines["p"], doc=doc, context=_ctx({"jobs": "not-list"}))


def test_command_on_error_recovers():
    cmd = CommandDef(
        run=RunSpec(program=sys.executable, argv=["-c", "import sys; sys.exit(5)"]),
        on_error=OnErrorSpec(steps=["recover"]),
    )
    doc = V2Document(commands={"main": cmd, "recover": _cmd_ok("recovered")})

    result = execute_command_def(doc.commands["main"], context=_ctx(), doc=doc, step_name="main")

    assert result.status == StepStatus.RECOVERED


def test_pipeline_on_error_recovered_and_failed_recovery():
    recover_ok_doc = V2Document(
        commands={"bad": _cmd_fail(), "recover": _cmd_ok()},
        pipelines={"p": PipelineDef(steps=["bad"], on_error=OnErrorSpec(steps=["recover"]))},
    )
    recovered = execute_pipeline_def(recover_ok_doc.pipelines["p"], doc=recover_ok_doc, context=_ctx())
    assert recovered.status == StepStatus.RECOVERED

    recover_bad_doc = V2Document(
        commands={"bad": _cmd_fail(), "recover": _cmd_fail(7)},
        pipelines={"p": PipelineDef(steps=["bad"], on_error=OnErrorSpec(steps=["recover"]))},
    )
    failed = execute_pipeline_def(recover_bad_doc.pipelines["p"], doc=recover_bad_doc, context=_ctx())
    assert failed.status == StepStatus.FAILED
    assert "recovery_error" in failed.meta
    assert failed.error is not None
