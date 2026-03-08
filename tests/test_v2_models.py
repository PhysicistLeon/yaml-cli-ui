# pylint: disable=import-error
import pytest

from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    LauncherDef,
    PipelineDef,
    RunSpec,
    StepKind,
    StepResult,
    StepSpec,
    StepStatus,
    V2Document,
)


def test_v2_document_minimal_model_shape():
    doc = V2Document(launchers={"hello": LauncherDef(title="Hello", use="hello_command")})

    assert doc.version == 2
    assert "hello" in doc.launchers


def test_v2_document_callables_merges_commands_and_pipelines():
    command = CommandDef(run=RunSpec(program="python"))
    pipeline = PipelineDef(steps=[])
    doc = V2Document(commands={"cmd": command}, pipelines={"pipe": pipeline})

    assert doc.callables() == {"cmd": command, "pipe": pipeline}


def test_launcher_requires_title_and_use():
    with pytest.raises(ValueError, match="title"):
        LauncherDef(title="", use="x")
    with pytest.raises(ValueError, match="use"):
        LauncherDef(title="X", use="")


def test_runspec_requires_program():
    with pytest.raises(ValueError, match="program"):
        RunSpec(program="")


def test_command_requires_run():
    with pytest.raises(ValueError, match="run"):
        CommandDef(run=None)  # type: ignore[arg-type]


def test_pipeline_allows_empty_steps_for_scaffold():
    pipeline = PipelineDef(steps=[])

    assert not pipeline.steps


def test_stepspec_kind_detects_use_and_foreach():
    use_step = StepSpec(use="commands.hello")
    foreach_step = StepSpec(
        foreach=ForeachSpec(in_expr=[1], as_name="item", steps=["commands.hello"])
    )

    assert use_step.kind == StepKind.USE
    assert use_step.is_use_step is True
    assert foreach_step.kind == StepKind.FOREACH
    assert foreach_step.is_foreach_step is True


def test_foreach_requires_as_name_and_non_empty_steps():
    with pytest.raises(ValueError, match="as_name"):
        ForeachSpec(in_expr=[1, 2], as_name="", steps=["x"])
    with pytest.raises(ValueError, match="steps"):
        ForeachSpec(in_expr=[1, 2], as_name="item", steps=[])


def test_step_status_values_match_expected_spec():
    assert {status.value for status in StepStatus} == {
        "success",
        "failed",
        "skipped",
        "recovered",
    }


def test_step_result_minimal_with_status_only():
    result = StepResult(name="build", status=StepStatus.SUCCESS)

    assert result.status is StepStatus.SUCCESS
    assert result.stdout is None
    assert result.stderr is None
    assert result.exit_code is None
