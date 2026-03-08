# pylint: disable=import-error

from __future__ import annotations

from pathlib import Path

import pytest

from yaml_cli_ui.v2.argv import (
    is_conditional_item,
    is_option_map,
    serialize_argv,
    serialize_argv_item,
)
from yaml_cli_ui.v2.errors import V2ExecutionError, V2ValidationError


@pytest.fixture
def ctx(tmp_path: Path) -> dict:
    return {
        "params": {
            "source_url": "https://example.com/video",
            "bitrate": "192K",
            "embed_thumb": True,
            "need_format": True,
        },
        "locals": {
            "urls_file": "/tmp/urls.json",
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
            }
        },
    }


def test_predicates():
    assert is_option_map({"--x": 1}) is True
    assert is_option_map({"": 1}) is False
    assert is_option_map({1: "x"}) is False
    assert is_option_map({"when": True, "then": "x"}) is False
    assert is_option_map({"--x": 1, "--y": 2}) is False

    assert is_conditional_item({"when": True, "then": "x"}) is True
    assert is_conditional_item({"when": True}) is False


def test_scalar_items(ctx: dict):
    assert serialize_argv_item("plain", ctx) == ["plain"]
    assert serialize_argv_item("a b c", ctx) == ["a b c"]
    assert serialize_argv_item("$params.source_url", ctx) == ["https://example.com/video"]
    assert serialize_argv_item(0, ctx) == ["0"]
    assert serialize_argv_item(False, ctx) == ["False"]


def test_option_map_shapes_and_values(ctx: dict):
    assert serialize_argv_item({"--audio-format": "mp3"}, ctx) == ["--audio-format", "mp3"]
    assert serialize_argv_item({"--limit": 0}, ctx) == ["--limit", "0"]
    assert serialize_argv_item({"--flag": True}, ctx) == ["--flag"]
    assert serialize_argv_item({"--flag": False}, ctx) == []
    assert serialize_argv_item({"--flag": None}, ctx) == []
    assert serialize_argv_item({"--flag": ""}, ctx) == []
    assert serialize_argv_item({"--item": []}, ctx) == []
    assert serialize_argv_item({"--item": ["a", "b"]}, ctx) == ["--item", "a", "--item", "b"]
    assert serialize_argv_item({"--flag": "false"}, ctx) == ["--flag", "false"]
    with pytest.raises(V2ExecutionError, match="must not be null"):
        serialize_argv_item({"--item": [1, None, 2]}, ctx)


def test_conditional_items(ctx: dict):
    assert serialize_argv_item({"when": True, "then": "--verbose"}, ctx) == ["--verbose"]
    assert serialize_argv_item({"when": False, "then": "--verbose"}, ctx) == []
    assert serialize_argv_item(
        {"when": "$params.embed_thumb", "then": "--embed-thumbnail"},
        ctx,
    ) == ["--embed-thumbnail"]
    assert serialize_argv_item(
        {"when": "$params.need_format", "then": {"--audio-format": "mp3"}},
        ctx,
    ) == ["--audio-format", "mp3"]




def test_conditional_then_disallows_nested_conditional(ctx: dict):
    with pytest.raises(V2ValidationError, match="then"):
        serialize_argv_item(
            {"when": True, "then": {"when": False, "then": "--x"}},
            ctx,
        )


def test_conditional_invalid_shapes(ctx: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"when": True}, ctx)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"then": "--x"}, ctx)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"when": True, "--x": 1}, ctx)


def test_invalid_shapes(ctx: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"--x": 1, "--y": 2}, ctx)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"": 1}, ctx)
    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$params", ctx)
    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$profile", ctx)


def test_no_shell_splitting(ctx: dict):
    assert serialize_argv_item("--name value with spaces", ctx) == ["--name value with spaces"]


def test_full_mixed_argv_with_context_refs(ctx: dict):
    argv = [
        "--extract-audio",
        {"--audio-format": "mp3"},
        {"--audio-quality": "$params.bitrate"},
        {"when": "$params.embed_thumb", "then": "--embed-thumbnail"},
        {"-o": "$profile.workdir/%(title)s.%(ext)s"},
        "$params.source_url",
        "$locals.urls_file",
        "$run.id",
        "$steps.scrape.stdout",
    ]

    assert serialize_argv(argv, ctx) == [
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
        "--embed-thumbnail",
        "-o",
        "/work/%(title)s.%(ext)s",
        "https://example.com/video",
        "/tmp/urls.json",
        "run_123",
        "ok",
    ]


def test_truthy_when_uses_python_truthiness(ctx: dict):
    assert serialize_argv_item({"when": 0, "then": "--x"}, ctx) == []
    assert serialize_argv_item({"when": [], "then": "--x"}, ctx) == []
    assert serialize_argv_item({"when": "0", "then": "--x"}, ctx) == ["--x"]


def test_serialize_argv_requires_list(ctx: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv("--x", ctx)  # type: ignore[arg-type]
