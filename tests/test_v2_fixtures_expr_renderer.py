# pylint: disable=import-error

import pytest

from tests.v2_test_utils import load_fixture_doc, runtime_context
from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.expr import evaluate_expression
from yaml_cli_ui.v2.renderer import render_scalar_or_ref, render_value


def test_explicit_namespaces_and_interpolation_from_fixture_context():
    doc = load_fixture_doc("valid_locals.yaml")
    ctx = runtime_context(doc, params={"collection": "demo"}, selected_profile_name="home")

    assert evaluate_expression("params.collection", ctx) == "demo"
    assert evaluate_expression("locals.run_root", ctx) == "/work/runs/demo"
    assert evaluate_expression("profile.workdir", ctx) == "/work"
    assert render_value("${locals.spool_dir}/urls.json", ctx) == "/work/runs/demo/spool/urls.json"


def test_escape_sequences_rendered_as_literals():
    ctx = {"params": {"x": "1"}}
    assert render_value("$$", ctx) == "$"
    assert render_value("$${", ctx) == "${"


def test_ambiguous_short_name_errors():
    ctx = {"params": {"x": 1}, "locals": {"x": 2}, "bindings": {}}
    with pytest.raises(V2ExpressionError, match="ambiguous"):
        evaluate_expression("x", ctx)


def test_allowed_and_disallowed_functions():
    ctx = {"params": {"items": [1], "none": None}, "locals": {"x": __file__}, "bindings": {}}

    assert evaluate_expression("len(params.items)", ctx) == 1
    assert evaluate_expression("empty(params.none)", ctx) is True
    assert evaluate_expression("exists(locals.x)", ctx) is True

    with pytest.raises(V2ExpressionError, match="not allowed"):
        evaluate_expression("upper(locals.x)", ctx)


def test_profile_and_params_short_ref_rendering():
    doc = load_fixture_doc("argv_mixed.yaml")
    ctx = runtime_context(doc, selected_profile_name="home", params={"source_url": "u", "bitrate": "128K", "embed_thumb": True})
    assert render_scalar_or_ref("$params.bitrate", ctx) == "128K"
