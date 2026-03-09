from pathlib import Path

import pytest

from tests.v2_test_utils import load_fixture_document, portable_python_replacements, runtime_context_mapping
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.executor import execute_pipeline_def
from yaml_cli_ui.v2.models import (
    CommandDef,
    OnErrorSpec,
    PipelineDef,
    RunSpec,
    StepSpec,
    StepStatus,
    V2Document,
)


def _py_cmd(code: str) -> CommandDef:
    return CommandDef(run=RunSpec(program="python", argv=["-c", code]))


def test_pipeline_fixture_success_and_nested_and_short_and_expanded(tmp_path: Path):
    doc = load_fixture_document("pipeline_success.yaml", replacements=portable_python_replacements(tmp_path))
    doc.commands["echo_bound"] = _py_cmd("import sys; print(sys.argv[1], sys.argv[2])")
    doc.pipelines["nested"] = PipelineDef(steps=["flow"])
    doc.commands["echo_bound"].run.argv.extend(["$mode", "$params.mode"])  # type: ignore[union-attr]

    ctx = runtime_context_mapping(doc, params={"mode": "param-mode"}, profile="test")

    simple = execute_pipeline_def(doc.pipelines["flow"], doc=doc, context=ctx)
    assert simple.status == StepStatus.SUCCESS

    nested = execute_pipeline_def(doc.pipelines["nested"], doc=doc, context=ctx)
    assert nested.status == StepStatus.SUCCESS
    assert "flow" in nested.children

    short_twice = execute_pipeline_def(PipelineDef(steps=["ok", "ok"]), doc=doc, context=ctx)
    assert list(short_twice.children.keys()) == ["ok", "ok_2"]

    expanded = execute_pipeline_def(
        PipelineDef(steps=[StepSpec(use="echo_bound", with_values={"mode": "with-mode"})]),
        doc=doc,
        context=ctx,
    )
    assert expanded.children["echo_bound"].status == StepStatus.SUCCESS
    assert "with-mode param-mode" in (expanded.children["echo_bound"].stdout or "")


def test_pipeline_failure_continue_on_error_and_when_false(tmp_path: Path):
    doc = load_fixture_document("pipeline_continue_on_error.yaml", replacements=portable_python_replacements(tmp_path))
    ctx = runtime_context_mapping(doc, profile="test", params={"jobs": [{"name": "alpha"}, {"name": "beta"}]})

    continued = execute_pipeline_def(doc.pipelines["flow"], doc=doc, context=ctx)
    assert continued.status == StepStatus.FAILED
    assert list(continued.children.keys()) == ["bad", "ok"]

    stopped = execute_pipeline_def(PipelineDef(steps=["bad", "ok"]), doc=doc, context=ctx)
    assert stopped.status == StepStatus.FAILED
    assert list(stopped.children.keys()) == ["bad"]

    skipped = execute_pipeline_def(
        PipelineDef(steps=[StepSpec(step="skip", use="ok", when="${false}"), "ok"]),
        doc=doc,
        context=ctx,
    )
    assert skipped.children["skip"].status == StepStatus.SKIPPED
    assert skipped.children["ok"].status == StepStatus.SUCCESS


def test_pipeline_foreach_success_and_invalid_input(tmp_path: Path):
    success_doc = load_fixture_document("foreach_success.yaml", replacements=portable_python_replacements(tmp_path))
    success_ctx = runtime_context_mapping(success_doc, params={"jobs": [{"name": "a"}, {"name": "b"}]}, profile="test")

    success = execute_pipeline_def(success_doc.pipelines["flow"], doc=success_doc, context=success_ctx)
    assert success.status == StepStatus.SUCCESS
    assert success.children["per_job"].meta["iteration_count"] == 2

    bad_doc = load_fixture_document("foreach_invalid_input.yaml", replacements=portable_python_replacements(tmp_path))
    bad_ctx = runtime_context_mapping(bad_doc, params={"jobs": "nope"}, profile="test")
    with pytest.raises(V2ExecutionError, match="foreach.in must evaluate to a list"):
        execute_pipeline_def(bad_doc.pipelines["flow"], doc=bad_doc, context=bad_ctx)


def test_pipeline_and_command_on_error_paths(tmp_path: Path):
    recovered_doc = load_fixture_document("pipeline_on_error_recovered.yaml", replacements=portable_python_replacements(tmp_path))
    recovered_ctx = runtime_context_mapping(recovered_doc, profile="test")
    recovered = execute_pipeline_def(recovered_doc.pipelines["flow"], doc=recovered_doc, context=recovered_ctx)
    assert recovered.status == StepStatus.RECOVERED

    doc = V2Document(
        commands={
            "bad": CommandDef(
                run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(5)"]),
                on_error=OnErrorSpec(steps=["recover"]),
            ),
            "bad_plain": CommandDef(
                run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(6)"]),
            ),
            "recover": _py_cmd("print('ok')"),
            "recover_bad": _py_cmd("import sys; sys.exit(8)"),
        },
        launchers={},
    )
    ctx = {
        "params": {},
        "locals": {},
        "profile": {"runtimes": {"python": portable_python_replacements()["__PYTHON__"]}},
        "run": {},
        "steps": {},
        "bindings": {},
    }

    command_recovered = execute_pipeline_def(PipelineDef(steps=["bad"]), doc=doc, context=ctx)
    assert command_recovered.children["bad"].status == StepStatus.RECOVERED

    failed_recovery = execute_pipeline_def(
        PipelineDef(steps=["bad_plain"], on_error=OnErrorSpec(steps=["recover_bad"])),
        doc=doc,
        context=ctx,
    )
    assert failed_recovery.status == StepStatus.FAILED
    assert failed_recovery.meta.get("recovery_error") is not None


def test_integration_like_full_ingest_fixture_smoke(tmp_path: Path):
    doc = load_fixture_document(
        "full_ingest_like.yaml",
        replacements=portable_python_replacements(tmp_path),
    )
    ctx = runtime_context_mapping(doc, profile="test", params={"jobs": [{"name": "alpha"}, {"name": "beta"}]})

    result = execute_pipeline_def(doc.pipelines["ingest"], doc=doc, context=ctx)

    assert result.status == StepStatus.SUCCESS
    assert (tmp_path / "out" / "alpha.txt").exists()
    assert (tmp_path / "out" / "beta.txt").exists()
