# pylint: disable=import-error

import pytest

from tests.v2_test_utils import load_fixture_doc, runtime_context
from yaml_cli_ui.v2.argv import serialize_argv
from yaml_cli_ui.v2.errors import V2ExecutionError


def test_scalar_only_argv_serialization():
    assert serialize_argv(["a", 0, False], {"params": {}, "locals": {}, "bindings": {}}) == ["a", "0", "False"]


def test_scalar_string_with_spaces_is_not_shell_split():
    ctx = {"params": {}, "locals": {}, "bindings": {}}
    assert serialize_argv(["--name value with spaces"], ctx) == ["--name value with spaces"]


def test_mixed_argv_fixture_serialization_and_scalar_ref_single_token():
    doc = load_fixture_doc("argv_mixed.yaml")
    cmd = doc.commands["download"]
    ctx = runtime_context(
        doc,
        selected_profile_name="home",
        params={"source_url": "https://e/x", "bitrate": "320K", "embed_thumb": True},
    )

    actual = serialize_argv(cmd.run.argv, ctx)
    assert actual == [
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "320K",
        "--embed-thumbnail",
        "-o",
        "/work/%(title)s.%(ext)s",
        "https://e/x",
    ]
    assert serialize_argv(["$params.source_url"], ctx) == ["https://e/x"]


def test_bool_null_empty_list_and_false_string_semantics():
    ctx = {"params": {}, "locals": {}, "bindings": {}}
    assert serialize_argv([{"--flag": True}, {"--none": None}, {"--empty": ""}, {"--n": 0}, "false", {"--list": [1, "x"]}], ctx) == [
        "--flag",
        "--n",
        "0",
        "false",
        "--list",
        "1",
        "--list",
        "x",
    ]


def test_invalid_argv_shapes_raise_errors():
    ctx = {"params": {}, "locals": {}, "bindings": {}}
    with pytest.raises(Exception, match="Invalid argv item shape"):
        serialize_argv([{"when": True}], ctx)
    with pytest.raises(Exception, match="Invalid argv item shape"):
        serialize_argv([{"then": "--x"}], ctx)
    with pytest.raises(Exception, match="Invalid argv item shape"):
        serialize_argv([{"--a": 1, "--b": 2}], ctx)
    with pytest.raises(V2ExecutionError, match="must be scalar"):
        serialize_argv(["$params.v"], {"params": {"v": [1]}, "locals": {}, "bindings": {}})
    with pytest.raises(V2ExecutionError, match="must be scalar"):
        serialize_argv(["$params.obj"], {"params": {"obj": {"a": 1}}, "locals": {}, "bindings": {}})
