import pytest

from tests.v2_test_utils import fixture_path, load_fixture_document, runtime_context_mapping
from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.expr import evaluate_expression
from yaml_cli_ui.v2.renderer import render_scalar_or_ref, render_string


def test_expression_and_renderer_namespaces_on_fixture_context():
    doc = load_fixture_document("valid_locals.yaml")
    ctx = runtime_context_mapping(doc, params={"collection": "music"}, profile="home")

    assert evaluate_expression("params.collection", ctx) == "music"
    assert evaluate_expression("locals.run_root", ctx) == "/work/runs/music"
    assert evaluate_expression("profile.workdir", ctx) == "/work"
    assert render_string("${locals.urls_file}", ctx) == "/work/runs/music/spool/urls.json"


def test_renderer_escape_sequences():
    ctx = {"params": {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}

    assert render_string("$$HOME", ctx) == "$HOME"
    assert render_string("$${params.x}", ctx) == "${params.x}"


def test_ambiguous_short_name_errors():
    ctx = {
        "params": {"x": 1},
        "locals": {"x": 2},
        "profile": {},
        "run": {},
        "steps": {},
        "bindings": {},
    }

    with pytest.raises(V2ExpressionError, match="ambiguous short name"):
        evaluate_expression("x", ctx)


def test_allowed_functions_and_disallowed_function():
    current_file = fixture_path("minimal_root.yaml")
    ctx = {
        "params": {"items": [1, 2], "none_value": None, "path": str(current_file)},
        "locals": {},
        "profile": {},
        "run": {},
        "steps": {},
        "bindings": {},
    }

    assert evaluate_expression("len(params.items)", ctx) == 2
    assert evaluate_expression("empty(params.none_value)", ctx) is True
    assert evaluate_expression("exists(params.path)", ctx) is True

    with pytest.raises(V2ExpressionError, match="not allowed"):
        evaluate_expression("sum(params.items)", ctx)


def test_scalar_ref_renderer_reads_locals():
    doc = load_fixture_document("valid_locals.yaml")
    ctx = runtime_context_mapping(doc, params={"collection": "incoming"}, profile="home")

    assert render_scalar_or_ref("$locals.urls_file", ctx) == "/work/runs/incoming/spool/urls.json"
