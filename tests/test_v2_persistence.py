# pylint: disable=import-error

import json

import pytest

from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.persistence import (
    LauncherPersistenceService,
    V2PersistenceError,
    get_v2_presets_path,
    get_v2_state_path,
    load_v2_presets,
    load_v2_state,
)


def _write_v2_yaml(path):
    path.write_text(
        """
version: 2
profiles:
  home: {}
params:
  username:
    type: string
  token:
    type: secret
commands:
  c:
    run:
      program: python
      argv: ["-c", "print('x')"]
launchers:
  l1:
    title: L1
    use: c
    with:
      username: fixed
""",
        encoding="utf-8",
    )


def test_paths_are_v2_specific(tmp_path):
    cfg = tmp_path / "config.yaml"
    presets = get_v2_presets_path(cfg)
    state = get_v2_state_path(cfg)
    assert presets.name.endswith(".launchers.presets.json")
    assert state.name.endswith(".state.json")
    assert presets.name != "config.yaml.presets.json"


def test_load_missing_files_returns_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    assert load_v2_presets(cfg) == {"version": 2, "launchers": {}}
    assert load_v2_state(cfg) == {"version": 2, "launchers": {}}


def test_roundtrip_presets_and_state(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_v2_yaml(cfg)
    doc = load_v2_document(cfg)
    svc = LauncherPersistenceService(cfg, doc)

    svc.upsert_preset("l1", "p1", {"username": "alice", "token": "secret"})
    loaded = load_v2_presets(cfg)
    assert loaded["launchers"]["l1"]["presets"]["p1"]["params"] == {}

    svc.set_selected_profile("home")
    svc.set_last_values("l1", {"username": "bob", "token": "secret2"})
    svc.set_last_selected_preset("l1", "p1")
    state = load_v2_state(cfg)
    assert state["selected_profile"] == "home"
    assert state["launchers"]["l1"]["last_values"] == {}
    assert state["launchers"]["l1"]["last_selected_preset"] == "p1"


def test_unknown_fields_ignored_on_get_preset(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_v2_yaml(cfg)
    doc = load_v2_document(cfg)
    presets_path = get_v2_presets_path(cfg)
    presets_path.write_text(
        json.dumps(
            {
                "version": 2,
                "launchers": {
                    "l1": {
                        "presets": {
                            "p": {
                                "params": {"unknown": 1, "username": "u", "token": "x"},
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    svc = LauncherPersistenceService(cfg, doc)
    assert svc.get_preset("l1", "p") == {}


def test_broken_json_tolerated_by_service(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_v2_yaml(cfg)
    doc = load_v2_document(cfg)
    get_v2_state_path(cfg).write_text("{broken", encoding="utf-8")

    svc = LauncherPersistenceService(cfg, doc)
    assert svc.load_state() == {"version": 2, "launchers": {}}
    assert svc.warnings

    with pytest.raises(V2PersistenceError):
        load_v2_state(cfg)


def test_atomic_save_outputs_valid_json(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_v2_yaml(cfg)
    doc = load_v2_document(cfg)
    svc = LauncherPersistenceService(cfg, doc)
    svc.set_selected_profile("home")

    content = get_v2_state_path(cfg).read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert parsed["version"] == 2
