# pylint: disable=import-error

from pathlib import Path

import pytest

from yaml_cli_ui.v2.errors import V2ExpressionError
from yaml_cli_ui.v2.renderer import render_scalar_or_ref, render_string, render_value


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
            }
        },
    }


def test_render_value_non_string(ctx):
    assert render_value(123, ctx) == 123


def test_render_value_full_ref_returns_native_int(ctx):
    assert render_value("$params.max_items", ctx) == 10


def test_render_value_full_ref_returns_native_list(ctx):
    assert render_value("$params.jobs", ctx) == [{"source_url": "a"}, {"source_url": "b"}]


def test_render_string_interpolation(ctx):
    assert render_string("${profile.workdir}\\runs\\${params.collection}", ctx) == "/work\\runs\\incoming"


def test_render_string_dollar_escape(ctx):
    assert render_string("$$message", ctx) == "$message"


def test_render_string_brace_escape(ctx):
    assert render_string("literal $${name}", ctx) == "literal ${name}"


def test_render_string_inline_expr(ctx):
    assert render_string("x=${params.count}", ctx) == "x=5"


def test_render_string_none_as_empty(ctx):
    assert render_string("x=${locals.maybe_none}", ctx) == "x="


def test_render_string_multiple_expressions(ctx):
    assert render_string("${params.collection}-${run.id}-${steps.scrape.exit_code}", ctx) == "incoming-run_123-0"


def test_render_scalar_or_ref_plain_text(ctx):
    assert render_scalar_or_ref("plain text", ctx) == "plain text"


def test_render_scalar_or_ref_non_string(ctx):
    assert render_scalar_or_ref(123, ctx) == 123


def test_render_scalar_or_ref_ambiguous_short_name_raises(ctx):
    ctx["params"]["urls_file"] = "a"
    with pytest.raises(V2ExpressionError, match="Ambiguous short name"):
        render_scalar_or_ref("$urls_file", ctx)
