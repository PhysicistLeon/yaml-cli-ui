import pytest

from tests.v2_test_utils import load_fixture_document, runtime_context_mapping
from yaml_cli_ui.v2.argv import serialize_argv
from yaml_cli_ui.v2.errors import V2ExecutionError, V2ValidationError


def test_scalar_only_argv_serialization():
    ctx = {"params": {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}

    assert serialize_argv(["abc", 0, False, "false"], ctx) == ["abc", "0", "False", "false"]


def test_mixed_argv_fixture_serialization():
    doc = load_fixture_document("argv_mixed.yaml")
    command = doc.commands["download"]
    ctx = runtime_context_mapping(doc, params={"embed_thumb": True, "bitrate": "192K", "source_url": "https://example.com/video"}, profile="home")

    argv = serialize_argv(command.run.argv, ctx)

    assert isinstance(argv, list)
    assert argv == [
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


def test_mixed_argv_bool_null_empty_list_cases():
    ctx = {"params": {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}

    argv = serialize_argv([
        {"--flag": True},
        {"--off": False},
        {"--null": None},
        {"--empty": ""},
        {"--many": ["a", 0, "false"]},
        0,
        "false",
    ], ctx)

    assert argv == ["--flag", "--many", "a", "--many", "0", "--many", "false", "0", "false"]


def test_invalid_argv_shapes():
    ctx = {"params": {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}

    with pytest.raises(V2ValidationError):
        serialize_argv([{"when": True}], ctx)
    with pytest.raises(V2ValidationError):
        serialize_argv([{"then": "--x"}], ctx)
    with pytest.raises(V2ValidationError):
        serialize_argv([{"--a": 1, "--b": 2}], ctx)
    with pytest.raises(V2ExecutionError):
        serialize_argv(["$params"], {**ctx, "params": {"x": 1}})
