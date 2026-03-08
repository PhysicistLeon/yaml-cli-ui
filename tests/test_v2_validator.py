# pylint: disable=import-error

import pytest

from yaml_cli_ui.v2.errors import V2ValidationError
from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    LauncherDef,
    OnErrorSpec,
    PipelineDef,
    RunSpec,
    StepSpec,
    V2Document,
)
from yaml_cli_ui.v2.validator import validate_v2_document


def _base_doc() -> V2Document:
    return V2Document(
        version=2,
        commands={"hello_command": CommandDef(run=RunSpec(program="python", argv=["-V"]))},
        launchers={"hello": LauncherDef(title="Hello", use="hello_command")},
    )


def test_valid_minimal_root_doc_passes():
    validate_v2_document(_base_doc())


def test_wrong_version_fails():
    doc = _base_doc()
    doc.version = 1

    with pytest.raises(V2ValidationError, match="expected 2"):
        validate_v2_document(doc)


def test_root_without_launchers_fails():
    doc = V2Document(version=2, commands={"hello_command": CommandDef(run=RunSpec(program="python", argv=["-V"]))})

    with pytest.raises(V2ValidationError, match="launchers"):
        validate_v2_document(doc)


def test_imported_doc_with_launchers_fails():
    doc = _base_doc()
    imported = V2Document(version=2, launchers={"x": LauncherDef(title="X", use="cmd")})
    doc.imported_documents = {"dep": imported}

    with pytest.raises(V2ValidationError, match="must not define launchers"):
        validate_v2_document(doc)


def test_imported_doc_with_profiles_fails():
    doc = _base_doc()
    imported = V2Document(version=2)
    imported.profiles = {"dev": object()}  # type: ignore[assignment]
    doc.imported_documents = {"dep": imported}

    with pytest.raises(V2ValidationError, match="must not define profiles"):
        validate_v2_document(doc)


def test_duplicate_callable_names_fail():
    doc = _base_doc()
    doc.pipelines = {"hello_command": PipelineDef(steps=["x"])}

    with pytest.raises(V2ValidationError, match="conflict"):
        validate_v2_document(doc)


def test_local_referencing_future_local_fails():
    doc = _base_doc()
    doc.locals = {"a": "$locals.b", "b": "ok"}

    with pytest.raises(V2ValidationError, match="future locals"):
        validate_v2_document(doc)


def test_valid_local_ordering_passes():
    doc = _base_doc()
    doc.locals = {"a": "1", "b": "$locals.a", "c": "${locals.b}"}

    validate_v2_document(doc)


def test_step_with_use_and_foreach_fails():
    doc = _base_doc()
    step = StepSpec(use="cmd")
    step.foreach = ForeachSpec(in_expr=[1], as_name="item", steps=["x"])
    doc.pipelines = {"pipe": PipelineDef(steps=[step])}

    with pytest.raises(V2ValidationError, match="exactly one"):
        validate_v2_document(doc)


def test_foreach_without_as_or_steps_fails():
    doc = _base_doc()
    foreach = ForeachSpec(in_expr=[1], as_name="x", steps=["x"])
    foreach.as_name = ""
    doc.pipelines = {"pipe": PipelineDef(steps=[StepSpec(foreach=foreach)])}

    with pytest.raises(V2ValidationError, match="foreach.as"):
        validate_v2_document(doc)

    foreach = ForeachSpec(in_expr=[1], as_name="x", steps=["x"])
    foreach.steps = []
    doc.pipelines = {"pipe": PipelineDef(steps=[StepSpec(foreach=foreach)])}

    with pytest.raises(V2ValidationError, match="foreach.steps"):
        validate_v2_document(doc)


def test_command_without_run_fails():
    doc = _base_doc()
    command = CommandDef(run=RunSpec(program="python", argv=["-V"]))
    command.run = None  # type: ignore[assignment]
    doc.commands = {"broken": command}

    with pytest.raises(V2ValidationError, match="run is required"):
        validate_v2_document(doc)


def test_command_with_non_list_argv_fails():
    doc = _base_doc()
    command = CommandDef(run=RunSpec(program="python", argv=["-V"]))
    command.run.argv = "-V"  # type: ignore[assignment]
    doc.commands = {"broken": command}

    with pytest.raises(V2ValidationError, match="argv"):
        validate_v2_document(doc)


def test_on_error_requires_non_empty_steps():
    doc = _base_doc()
    command = CommandDef(run=RunSpec(program="python", argv=["-V"]))
    on_error = OnErrorSpec(steps=["cleanup"])
    on_error.steps = []
    command.on_error = on_error
    doc.commands = {"broken": command}

    with pytest.raises(V2ValidationError, match="on_error.steps"):
        validate_v2_document(doc)
