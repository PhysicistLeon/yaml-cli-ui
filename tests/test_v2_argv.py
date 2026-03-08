# pylint: disable=import-error

from __future__ import annotations

import pytest

from yaml_cli_ui.v2.argv import (
    is_conditional_item,
    is_option_map,
    serialize_argv,
    serialize_argv_item,
)
from yaml_cli_ui.v2.errors import V2ExecutionError, V2ValidationError


@pytest.fixture
def context() -> dict:
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


def test_scalar_items(context: dict):
    assert serialize_argv_item("plain", context) == ["plain"]
    assert serialize_argv_item("a b c", context) == ["a b c"]
    assert serialize_argv_item("$params.source_url", context) == ["https://example.com/video"]
    assert serialize_argv_item(0, context) == ["0"]
    assert serialize_argv_item(False, context) == ["False"]


def test_option_map_shapes_and_values(context: dict):
    assert serialize_argv_item({"--audio-format": "mp3"}, context) == ["--audio-format", "mp3"]
    assert serialize_argv_item({"--limit": 0}, context) == ["--limit", "0"]
    assert serialize_argv_item({"--flag": True}, context) == ["--flag"]
    assert serialize_argv_item({"--flag": False}, context) == []
    assert serialize_argv_item({"--flag": None}, context) == []
    assert serialize_argv_item({"--flag": ""}, context) == []
    assert serialize_argv_item({"--item": []}, context) == []
    assert serialize_argv_item({"--item": ["a", "b"]}, context) == ["--item", "a", "--item", "b"]
    assert serialize_argv_item({"--flag": "false"}, context) == ["--flag", "false"]
    with pytest.raises(V2ExecutionError, match="must not be null"):
        serialize_argv_item({"--item": [1, None, 2]}, context)


def test_conditional_items(context: dict):
    assert serialize_argv_item({"when": True, "then": "--verbose"}, context) == ["--verbose"]
    assert serialize_argv_item({"when": False, "then": "--verbose"}, context) == []
    assert serialize_argv_item(
        {"when": "$params.embed_thumb", "then": "--embed-thumbnail"},
        context,
    ) == ["--embed-thumbnail"]
    assert serialize_argv_item(
        {"when": "$params.need_format", "then": {"--audio-format": "mp3"}},
        context,
    ) == ["--audio-format", "mp3"]




def test_conditional_then_disallows_nested_conditional(context: dict):
    with pytest.raises(V2ValidationError, match="then"):
        serialize_argv_item(
            {"when": True, "then": {"when": False, "then": "--x"}},
            context,
        )


def test_conditional_invalid_shapes(context: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"when": True}, context)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"then": "--x"}, context)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"when": True, "--x": 1}, context)


def test_invalid_shapes(context: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"--x": 1, "--y": 2}, context)
    with pytest.raises(V2ValidationError):
        serialize_argv_item({"": 1}, context)
    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$params", context)
    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$profile", context)


def test_no_shell_splitting(context: dict):
    assert serialize_argv_item("--name value with spaces", context) == ["--name value with spaces"]


def test_full_mixed_argv_with_context_refs(context: dict):
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

    assert serialize_argv(argv, context) == [
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


def test_truthy_when_uses_python_truthiness(context: dict):
    assert serialize_argv_item({"when": 0, "then": "--x"}, context) == []
    assert serialize_argv_item({"when": [], "then": "--x"}, context) == []
    assert serialize_argv_item({"when": "0", "then": "--x"}, context) == ["--x"]


def test_serialize_argv_requires_list(context: dict):
    with pytest.raises(V2ValidationError):
        serialize_argv("--x", context)  # type: ignore[arg-type]
