# pylint: disable=import-error

from pathlib import Path

import pytest

from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.expr import evaluate_expression, extract_local_refs, resolve_name


@pytest.fixture
def ctx(tmp_path: Path):
    urls_file = tmp_path / "urls.json"
    urls_file.write_text("[]", encoding="utf-8")
    return {
        "params": {
            "source_url": "https://example.com",
            "collection": "incoming",
            "mode": "video",
            "jobs": [{"source_url": "a"}, {"source_url": "b"}],
            "count": 5,
            "max_items": 10,
        },
        "locals": {
            "urls_file": str(urls_file),
            "run_root": "/tmp/run_1",
            "maybe_none": None,
        },
        "profile": {
            "workdir": "/work",
        },
        "run": {
            "id": "run_123",
        },
        "steps": {
            "scrape": {
                "stdout": "ok",
                "exit_code": 0,
            },
            "per_job": {
                "iterations": ["one", "two"],
            },
        },
    }


def test_evaluate_basic_bool(ctx):
    assert evaluate_expression("1 == 1", ctx) is True


def test_evaluate_compare_params(ctx):
    assert evaluate_expression("params.mode == 'video'", ctx) is True


def test_empty_and_not(ctx):
    assert evaluate_expression("not empty(params.jobs)", ctx) is True


def test_len_function(ctx):
    assert evaluate_expression("len(params.jobs)", ctx) == 2


def test_exists_function(ctx):
    assert evaluate_expression("exists(locals.urls_file)", ctx) is True


def test_dotted_access(ctx):
    assert evaluate_expression("steps.scrape.exit_code == 0", ctx) is True


def test_index_access(ctx):
    assert evaluate_expression("params.jobs[0].source_url", ctx) == "a"


def test_wrapped_expression(ctx):
    assert evaluate_expression("${params.collection}", ctx) == "incoming"


def test_unknown_name_raises(ctx):
    with pytest.raises(V2ExpressionError, match="Unknown name"):
        evaluate_expression("unknown_value", ctx)


def test_ambiguous_short_name_raises(ctx):
    ctx["params"]["urls_file"] = "a"
    with pytest.raises(V2ExpressionError, match="Ambiguous short name"):
        resolve_name("urls_file", ctx)


def test_disallowed_function_call_raises(ctx):
    with pytest.raises(V2ExpressionError, match="not allowed"):
        evaluate_expression("str(params.count)", ctx)


def test_disallowed_ast_node_raises(ctx):
    with pytest.raises(V2ExpressionError, match="Unsupported AST node"):
        evaluate_expression("[x for x in params.jobs]", ctx)


def test_short_name_resolution_namespaced(ctx):
    assert resolve_name("params.urls_file", {**ctx, "params": {**ctx["params"], "urls_file": "a"}}) == "a"
    assert resolve_name("locals.urls_file", ctx) == ctx["locals"]["urls_file"]


def test_extract_local_refs():
    assert "run_root" in extract_local_refs("${locals.run_root}\\x")
    assert "urls_file" in extract_local_refs("$locals.urls_file")
    assert extract_local_refs("plain") == set()
