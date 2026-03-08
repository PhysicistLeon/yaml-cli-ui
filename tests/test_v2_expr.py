# pylint: disable=import-error

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.expr import evaluate_expression, extract_local_refs, resolve_name


@dataclass
class Box:
    value: int


def _ctx(tmp_path: Path):
    return {
        "params": {
            "source_url": "https://example.com",
            "collection": "incoming",
            "mode": "video",
            "jobs": [{"source_url": "a"}, {"source_url": "b"}],
            "count": 5,
            "max_items": 10,
            "box": Box(value=9),
        },
        "locals": {
            "urls_file": str(tmp_path / "urls.json"),
            "run_root": "/tmp/run_1",
            "empty_list": [],
        },
        "profile": {"workdir": "/work"},
        "run": {"id": "run_123"},
        "steps": {"scrape": {"stdout": "ok", "exit_code": 0}, "per_job": {"iterations": [1, 2]}},
        "loop": {"index": 0},
        "error": {"message": "boom"},
    }


def test_evaluate_basic_boolean(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert evaluate_expression("1 == 1", ctx) is True


def test_evaluate_namespace_expression(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert evaluate_expression("params.mode == 'video'", ctx) is True


def test_evaluate_empty_and_len(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert evaluate_expression("not empty(params.jobs)", ctx) is True
    assert evaluate_expression("len(params.jobs)", ctx) == 2


def test_evaluate_exists_and_wrapper(tmp_path: Path):
    ctx = _ctx(tmp_path)
    path = Path(ctx["locals"]["urls_file"])
    path.write_text("{}", encoding="utf-8")
    assert evaluate_expression("exists(locals.urls_file)", ctx) is True
    assert evaluate_expression("${params.collection}", ctx) == "incoming"


def test_dotted_and_index_access(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert evaluate_expression("steps.scrape.exit_code", ctx) == 0
    assert evaluate_expression("steps.per_job.iterations[0]", ctx) == 1
    assert evaluate_expression("params.jobs[0].source_url", ctx) == "a"
    assert evaluate_expression("params.box.value", ctx) == 9


def test_unknown_and_ambiguous_names_raise(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ctx["params"]["urls_file"] = "param_urls"
    with pytest.raises(V2ExpressionError, match="unresolved"):
        resolve_name("missing", ctx)
    with pytest.raises(V2ExpressionError, match="ambiguous"):
        resolve_name("urls_file", ctx)


def test_disallowed_function_and_ast_nodes_raise(tmp_path: Path):
    ctx = _ctx(tmp_path)
    with pytest.raises(V2ExpressionError, match="not allowed"):
        evaluate_expression("sum(params.jobs)", ctx)
    with pytest.raises(V2ExpressionError, match="unsupported AST node"):
        evaluate_expression("[x for x in params.jobs]", ctx)


def test_short_name_resolution(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ctx["params"]["urls_file"] = "a"
    assert resolve_name("params.urls_file", ctx) == "a"
    assert resolve_name("locals.urls_file", ctx) == ctx["locals"]["urls_file"]
    with pytest.raises(V2ExpressionError, match="ambiguous"):
        resolve_name("urls_file", ctx)


def test_extract_local_refs():
    assert "run_root" in extract_local_refs("${locals.run_root}\\x")
    assert "urls_file" in extract_local_refs("$locals.urls_file")
    assert extract_local_refs("plain") == set()
