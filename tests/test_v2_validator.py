# pylint: disable=import-error

import pytest

from yaml_cli_ui.v2.errors import V2ValidationError
from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    LauncherDef,
    PipelineDef,
    RunSpec,
    StepSpec,
    V2Document,
)
from yaml_cli_ui.v2.validator import validate_v2_document


def _minimal_doc() -> V2Document:
    return V2Document(
        version=2,
        commands={"hello_command": CommandDef(run=RunSpec(program="python", argv=["-V"]))},
        launchers={"hello": LauncherDef(title="Hello", use="hello_command")},
    )


def test_valid_minimal_root_doc_passes():
    validate_v2_document(_minimal_doc())


def test_invalid_version_fails():
    doc = _minimal_doc()
    doc.version = 1
    with pytest.raises(V2ValidationError, match="expected 2"):
        validate_v2_document(doc)


def test_root_without_launchers_fails():
    doc = _minimal_doc()
    doc.launchers = {}
    with pytest.raises(V2ValidationError, match="launchers"):
        validate_v2_document(doc)


def test_imported_doc_with_launchers_fails():
    doc = _minimal_doc()
    imported = V2Document(launchers={"x": LauncherDef(title="X", use="c")})
    doc.imported_documents = {"lib": imported}
    with pytest.raises(V2ValidationError, match="must not define 'launchers'"):
        validate_v2_document(doc)


def test_imported_doc_with_profiles_fails():
    doc = _minimal_doc()
    imported = V2Document(profiles={"p": object()})  # type: ignore[dict-item]
    doc.imported_documents = {"lib": imported}
    with pytest.raises(V2ValidationError, match="must not define 'profiles'"):
        validate_v2_document(doc)


def test_duplicate_callable_names_fail():
    doc = _minimal_doc()
    doc.pipelines = {"hello_command": PipelineDef(steps=["x"])}
    with pytest.raises(V2ValidationError, match="duplicate names"):
        validate_v2_document(doc)


def test_local_referencing_future_local_fails():
    doc = _minimal_doc()
    doc.locals = {"a": "$locals.b", "b": "ok"}
    with pytest.raises(V2ValidationError, match="not-yet-defined"):
        validate_v2_document(doc)


def test_valid_local_ordering_passes():
    doc = _minimal_doc()
    doc.locals = {"a": "ok", "b": "${locals.a}"}
    validate_v2_document(doc)


def test_pipeline_step_with_use_and_foreach_fails():
    doc = _minimal_doc()
    step = StepSpec(use="some_command")
    step.foreach = ForeachSpec(in_expr="$params.items", as_name="item", steps=["some_command"])
    doc.pipelines = {"p": PipelineDef(steps=[step])}
    with pytest.raises(V2ValidationError, match="exactly one"):
        validate_v2_document(doc)


def test_foreach_without_as_or_steps_fails():
    doc = _minimal_doc()
    foreach = ForeachSpec(in_expr="$params.items", as_name="item", steps=["some_command"])
    foreach.as_name = ""
    foreach.steps = []
    doc.pipelines = {"p": PipelineDef(steps=[StepSpec(foreach=foreach)])}
    with pytest.raises(V2ValidationError, match="foreach.as"):
        validate_v2_document(doc)


def test_command_without_run_fails():
    doc = _minimal_doc()
    cmd = CommandDef(run=RunSpec(program="python", argv=["-V"]))
    cmd.run = None  # type: ignore[assignment]
    doc.commands = {"bad": cmd}
    with pytest.raises(V2ValidationError, match="must define 'run'"):
        validate_v2_document(doc)


def test_command_with_non_list_argv_fails():
    doc = _minimal_doc()
    doc.commands = {"bad": CommandDef(run=RunSpec(program="python", argv="-V"))}  # type: ignore[arg-type]
    with pytest.raises(V2ValidationError, match="run.argv"):
        validate_v2_document(doc)
