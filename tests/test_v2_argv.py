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


def _ctx(tmp_path: Path) -> dict:
    return {
        "params": {
            "source_url": "https://example.com/video",
            "bitrate": "192K",
            "embed_thumb": True,
            "need_format": True,
        },
        "locals": {"urls_file": str(tmp_path / "urls.json")},
        "profile": {"workdir": "/work"},
        "run": {"id": "run_123"},
        "steps": {"scrape": {"stdout": "ok"}},
    }


def test_scalar_items(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert serialize_argv_item("plain", ctx) == ["plain"]
    assert serialize_argv_item("a b c", ctx) == ["a b c"]
    assert serialize_argv_item("$params.source_url", ctx) == ["https://example.com/video"]
    assert serialize_argv_item(0, ctx) == ["0"]
    assert serialize_argv_item(False, ctx) == ["False"]


def test_option_map_items(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert serialize_argv_item({"--audio-format": "mp3"}, ctx) == ["--audio-format", "mp3"]
    assert serialize_argv_item({"--limit": 0}, ctx) == ["--limit", "0"]
    assert serialize_argv_item({"--flag": True}, ctx) == ["--flag"]
    assert serialize_argv_item({"--flag": False}, ctx) == []
    assert serialize_argv_item({"--flag": None}, ctx) == []
    assert serialize_argv_item({"--flag": ""}, ctx) == []
    assert serialize_argv_item({"--item": []}, ctx) == []
    assert serialize_argv_item({"--item": ["a", "b"]}, ctx) == ["--item", "a", "--item", "b"]
    assert serialize_argv_item({"--flag": "false"}, ctx) == ["--flag", "false"]


def test_conditional_items(tmp_path: Path):
    ctx = _ctx(tmp_path)
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


@pytest.mark.parametrize(
    "item",
    [
        {"when": True},
        {"then": "--x"},
        {"when": True, "--x": 1},
        {"a": 1, "b": 2},
        {"": "x"},
    ],
)
def test_invalid_shapes_raise_validation_error(item: dict, tmp_path: Path):
    with pytest.raises(V2ValidationError):
        serialize_argv_item(item, _ctx(tmp_path))


def test_scalar_resolving_to_list_or_dict_raises(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ctx["params"]["value_list"] = ["a", "b"]
    ctx["params"]["value_dict"] = {"k": "v"}

    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$params.value_list", ctx)
    with pytest.raises(V2ExecutionError):
        serialize_argv_item("$params.value_dict", ctx)


def test_no_shell_splitting(tmp_path: Path):
    assert serialize_argv_item("--name value with spaces", _ctx(tmp_path)) == ["--name value with spaces"]


def test_mixed_integration_with_context(tmp_path: Path):
    ctx = _ctx(tmp_path)
    argv = [
        "--extract-audio",
        {"--audio-format": "mp3"},
        {"--audio-quality": "$params.bitrate"},
        {"when": "$params.embed_thumb", "then": "--embed-thumbnail"},
        {"-o": "$profile.workdir/%(title)s.%(ext)s"},
        "$params.source_url",
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
    ]


def test_shape_detector_helpers():
    assert is_option_map({"--x": 1}) is True
    assert is_option_map({"when": True}) is False
    assert is_conditional_item({"when": True, "then": "--x"}) is True
    assert is_conditional_item({"when": True, "then": "--x", "else": "--y"}) is False
