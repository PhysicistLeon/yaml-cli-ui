# pylint: disable=import-error
from yaml_cli_ui.v2.models import LauncherDef, RunContext, V2Document


def test_v2_document_minimal_model_shape():
    doc = V2Document(
        raw={"version": 2, "launchers": {}},
        version=2,
        launchers={"hello": LauncherDef(title="Hello", use="hello_command")},
    )

    assert doc.version == 2
    assert "hello" in doc.launchers


def test_run_context_defaults():
    ctx = RunContext()

    assert ctx.params == {}
    assert ctx.locals == {}
    assert ctx.step_results == {}
