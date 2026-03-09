from tests.v2_test_utils import load_fixture_doc, runtime_context
from yaml_cli_ui.v2.executor import execute_pipeline_def
from yaml_cli_ui.v2.validator import validate_v2_document


def test_full_ingest_like_smoke_load_validate_and_run():
    doc = load_fixture_doc("full_ingest_like.yaml")
    validate_v2_document(doc)

    result = execute_pipeline_def(
        doc.pipelines["ingest"],
        doc=doc,
        context=runtime_context(doc, selected_profile_name="default", params={"collection": "inbox", "jobs": [{"name": "x"}]}),
    )

    assert result.status.value in {"success", "recovered"}
    assert "prep" in result.children
