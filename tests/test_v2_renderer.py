# pylint: disable=import-error

from __future__ import annotations

from pathlib import Path

import pytest

from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.renderer import render_scalar_or_ref, render_string, render_value


def _ctx(tmp_path: Path):
    return {
        "params": {
            "source_url": "https://example.com",
            "collection": "incoming",
            "mode": "video",
            "jobs": [{"source_url": "a"}, {"source_url": "b"}],
            "count": 5,
            "max_items": 10,
            "none_value": None,
        },
        "locals": {
            "urls_file": str(tmp_path / "urls.json"),
            "run_root": "/tmp/run_1",
        },
        "profile": {"workdir": "/work"},
        "run": {"id": "run_123"},
        "steps": {"scrape": {"stdout": "ok", "exit_code": 0}},
        "loop": {"index": 0},
        "error": {"message": "boom"},
    }


def test_render_value_passthrough_non_string(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert render_value(123, ctx) == 123


def test_render_scalar_or_ref_returns_native_types(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert render_scalar_or_ref("$params.max_items", ctx) == 10
    assert render_scalar_or_ref("$params.jobs", ctx) == ctx["params"]["jobs"]
    assert render_scalar_or_ref("$locals.urls_file", ctx) == ctx["locals"]["urls_file"]
    assert render_scalar_or_ref("plain text", ctx) == "plain text"
    assert render_scalar_or_ref(123, ctx) == 123


def test_render_string_interpolation(tmp_path: Path):
    ctx = _ctx(tmp_path)
    rendered = render_string("${profile.workdir}\\runs\\${params.collection}", ctx)
    assert rendered == "/work\\runs\\incoming"


def test_render_string_escaping(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert render_string("$$message", ctx) == "$message"
    assert render_string("literal $${name}", ctx) == "literal ${name}"


def test_render_string_expression_behaviour(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert render_string("x=${params.count}", ctx) == "x=5"
    assert render_string("a=${params.collection};b=${run.id}", ctx) == "a=incoming;b=run_123"
    assert render_string("none=${params.none_value}", ctx) == "none="


def test_render_short_name_ambiguity_raises(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ctx["params"]["urls_file"] = "a"
    with pytest.raises(V2ExpressionError, match="ambiguous"):
        render_scalar_or_ref("$urls_file", ctx)


def test_render_string_nested_braces_expression(tmp_path: Path):
    ctx = _ctx(tmp_path)
    rendered = render_string("value=${{'k': params.count}['k']}", ctx)
    assert rendered == "value=5"


def test_render_value_recursion_for_list_and_dict(tmp_path: Path):
    ctx = _ctx(tmp_path)
    value = {
        "a": ["$params.max_items", "x=${params.count}"],
        "b": {"nested": "$locals.urls_file"},
    }
    rendered = render_value(value, ctx)
    assert rendered == {
        "a": [10, "x=5"],
        "b": {"nested": ctx["locals"]["urls_file"]},
    }
