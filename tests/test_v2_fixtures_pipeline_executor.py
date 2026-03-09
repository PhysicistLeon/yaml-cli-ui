import pytest

from v2_test_utils import load_fixture_doc, runtime_context
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.executor import execute_pipeline_def
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


def _ctx(params=None):
    return {"params": params or {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}


def test_pipeline_fixtures_success_continue_recovered_foreach_and_invalid_input():
    success_doc = load_fixture_doc("pipeline_success.yaml")
    success = execute_pipeline_def(success_doc.pipelines["simple"], doc=success_doc, context=runtime_context(success_doc))
    assert success.status == StepStatus.SUCCESS

    cont_doc = load_fixture_doc("pipeline_continue_on_error.yaml")
    cont = execute_pipeline_def(cont_doc.pipelines["continue_case"], doc=cont_doc, context=runtime_context(cont_doc))
    assert cont.children["fail"].status == StepStatus.FAILED
    assert cont.children["ok"].status == StepStatus.SUCCESS
    assert cont.status == StepStatus.FAILED

    rec_doc = load_fixture_doc("pipeline_on_error_recovered.yaml")
    rec = execute_pipeline_def(rec_doc.pipelines["recoverable"], doc=rec_doc, context=runtime_context(rec_doc))
    assert rec.status == StepStatus.RECOVERED

    f_doc = load_fixture_doc("foreach_success.yaml")
    f_result = execute_pipeline_def(f_doc.pipelines["foreach_ok"], doc=f_doc, context=runtime_context(f_doc, params={"jobs": [{"name": "a"}, {"name": "b"}]}))
    assert f_result.children["each_job"].meta["iteration_count"] == 2

    bad_doc = load_fixture_doc("foreach_invalid_input.yaml")
    with pytest.raises(V2ExecutionError, match="foreach.in must evaluate to a list"):
        execute_pipeline_def(bad_doc.pipelines["foreach_bad"], doc=bad_doc, context=runtime_context(bad_doc, params={"jobs": "x"}))


def test_nested_short_expanded_when_false_on_error_and_failed_recovery_paths():
    doc = V2Document(
        commands={
            "ok": CommandDef(run=RunSpec(program="python", argv=["-c", "print('ok')"])),
            "bad": CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(7)"])),
            "recover": CommandDef(run=RunSpec(program="python", argv=["-c", "print('recover')"])),
            "recover_bad": CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(2)"])),
        },
        pipelines={
            "inner": PipelineDef(steps=["ok"]),
            "main": PipelineDef(
                steps=[
                    "inner",
                    StepSpec(step="skip", use="ok", when=False),
                    StepSpec(step="expanded", use="ok", with_values={"x": 1}),
                    StepSpec(step="fail", use="bad", continue_on_error=True),
                ],
                on_error=OnErrorSpec(steps=["recover"]),
            ),
            "main_bad_recovery": PipelineDef(steps=["bad"], on_error=OnErrorSpec(steps=["recover_bad"])),
            "with_foreach": PipelineDef(steps=[StepSpec(step="loop", foreach=ForeachSpec(in_expr="$params.jobs", as_name="job", steps=["ok"]))]),
        },
    )

    main = execute_pipeline_def(doc.pipelines["main"], doc=doc, context=_ctx())
    assert main.children["inner"].status == StepStatus.SUCCESS
    assert main.children["skip"].status == StepStatus.SKIPPED
    assert main.children["expanded"].status == StepStatus.SUCCESS
    assert main.children["fail"].status == StepStatus.FAILED
    assert main.status == StepStatus.FAILED

    failed_recovery = execute_pipeline_def(doc.pipelines["main_bad_recovery"], doc=doc, context=_ctx())
    assert failed_recovery.status == StepStatus.FAILED
    assert failed_recovery.meta.get("recovery_error") is not None
