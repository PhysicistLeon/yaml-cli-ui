import json
import tkinter as tk
from pathlib import Path

import pytest

from yaml_cli_ui.app_v2 import AppV2
from yaml_cli_ui.v2.models import LauncherDef, ParamDef, ParamType, V2Document
from yaml_cli_ui.v2.persistence import (
    LauncherPersistenceService,
    V2PersistenceError,
    get_v2_presets_path,
    get_v2_state_path,
    load_v2_presets,
    load_v2_state,
    save_v2_presets,
    save_v2_state,
    sanitize_param_values_for_storage,
)


def _doc() -> V2Document:
    return V2Document(
        params={
            "name": ParamDef(type=ParamType.STRING),
            "token": ParamDef(type=ParamType.SECRET),
            "mode": ParamDef(type=ParamType.STRING),
        },
        launchers={
            "ingest": LauncherDef(title="Ingest", use="cmd", with_values={"mode": "fixed"}),
        },
    )


def test_v2_paths_are_stable_and_distinct(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    assert get_v2_presets_path(cfg).name == "config.yaml.launchers.presets.json"
    assert get_v2_state_path(cfg).name == "config.yaml.state.json"
    assert get_v2_presets_path(cfg).name != "config.yaml.presets.json"


def test_load_missing_files_returns_defaults(tmp_path: Path):
    cfg = tmp_path / "missing.yaml"
    assert load_v2_presets(cfg) == {"version": 2, "launchers": {}}
    assert load_v2_state(cfg) == {"version": 2, "selected_profile": None, "launchers": {}}


def test_presets_roundtrip(tmp_path: Path):
    cfg = tmp_path / "a.yaml"
    payload = {
        "version": 2,
        "launchers": {
            "ingest": {
                "presets": {
                    "default": {"params": {"name": "alice"}},
                }
            }
        },
    }
    save_v2_presets(cfg, payload)
    assert load_v2_presets(cfg) == payload


def test_state_roundtrip(tmp_path: Path):
    cfg = tmp_path / "a.yaml"
    payload = {
        "version": 2,
        "selected_profile": "home",
        "launchers": {
            "ingest": {
                "last_values": {"name": "alice"},
                "last_selected_preset": "default",
            }
        },
    }
    save_v2_state(cfg, payload)
    assert load_v2_state(cfg) == payload


def test_secret_sanitization_strips_secret_and_with_values():
    doc = _doc()
    values = {"name": "alice", "token": "plain", "mode": "override", "ghost": "x"}
    assert sanitize_param_values_for_storage(doc, "ingest", values) == {"name": "alice"}


def test_unknown_fields_ignored_on_apply_and_get_preset(tmp_path: Path):
    service = LauncherPersistenceService(tmp_path / "x.yaml", _doc())
    service.load_presets()
    service._presets["launchers"] = {
        "ingest": {"presets": {"p1": {"params": {"name": "alice", "ghost": 1, "token": "x", "mode": "x"}}}}
    }
    assert service.get_preset("ingest", "p1") == {"params": {"name": "alice"}}
    assert service.apply_preset_values("ingest", "p1") == {"name": "alice"}


def test_broken_json_raises_and_service_falls_back_with_warnings(tmp_path: Path):
    cfg = tmp_path / "bad.yaml"
    get_v2_presets_path(cfg).write_text("{oops", encoding="utf-8")
    get_v2_state_path(cfg).write_text("{oops", encoding="utf-8")
    with pytest.raises(V2PersistenceError):
        load_v2_presets(cfg)
    with pytest.raises(V2PersistenceError):
        load_v2_state(cfg)

    service = LauncherPersistenceService(cfg, _doc())
    assert service.load_presets() == {"version": 2, "launchers": {}}
    assert service.load_state() == {"version": 2, "selected_profile": None, "launchers": {}}
    assert len(service.warnings) == 2
    assert service.last_warning is not None


def test_invalid_version_and_structure_errors(tmp_path: Path):
    cfg = tmp_path / "badshape.yaml"

    get_v2_presets_path(cfg).write_text('{"version": 1, "launchers": {}}', encoding="utf-8")
    with pytest.raises(V2PersistenceError):
        load_v2_presets(cfg)

    get_v2_state_path(cfg).write_text('{"version": 1, "launchers": {}}', encoding="utf-8")
    with pytest.raises(V2PersistenceError):
        load_v2_state(cfg)

    get_v2_state_path(cfg).write_text('{"version": 2, "selected_profile": 123, "launchers": {}}', encoding="utf-8")
    with pytest.raises(V2PersistenceError):
        load_v2_state(cfg)

    get_v2_presets_path(cfg).write_text('{"version": 2, "launchers": []}', encoding="utf-8")
    with pytest.raises(V2PersistenceError):
        load_v2_presets(cfg)

    get_v2_state_path(cfg).write_text(
        '{"version": 2, "launchers": {"ingest": {"last_values": []}}}',
        encoding="utf-8",
    )
    with pytest.raises(V2PersistenceError):
        load_v2_state(cfg)


def test_service_fallback_on_invalid_structure(tmp_path: Path):
    cfg = tmp_path / "broken.json"
    get_v2_presets_path(cfg).write_text('{"version": 2, "launchers": []}', encoding="utf-8")
    get_v2_state_path(cfg).write_text(
        '{"version": 2, "selected_profile": 123, "launchers": {}}',
        encoding="utf-8",
    )
    service = LauncherPersistenceService(cfg, _doc())
    assert service.load_presets() == {"version": 2, "launchers": {}}
    assert service.load_state() == {"version": 2, "selected_profile": None, "launchers": {}}
    assert len(service.warnings) == 2


def test_atomic_save_writes_valid_json_over_multiple_cycles(tmp_path: Path):
    cfg = tmp_path / "atomic.yaml"
    service = LauncherPersistenceService(cfg, _doc())
    service.load_presets()

    for idx in range(5):
        service.upsert_preset("ingest", f"p{idx}", {"name": f"alice-{idx}", "token": "secret"})
        text = get_v2_presets_path(cfg).read_text(encoding="utf-8")
        parsed = json.loads(text)
        assert parsed["version"] == 2
        assert "launchers" in parsed

    loaded = load_v2_presets(cfg)
    assert loaded["launchers"]["ingest"]["presets"]["p4"]["params"] == {"name": "alice-4"}


def _maybe_app(path: Path):
    try:
        app = AppV2(str(path))
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    app.withdraw()
    return app


def test_app_v2_reads_and_writes_selected_profile_state(tmp_path: Path):
    cfg = tmp_path / "ui.yaml"
    cfg.write_text(
        """
version: 2
profiles:
  home: {}
  work: {}
commands:
  c:
    run:
      program: "python"
      argv: ["-c", "print('ok')"]
launchers:
  l:
    title: L
    use: c
""",
        encoding="utf-8",
    )
    save_v2_state(
        cfg,
        {"version": 2, "selected_profile": "work", "launchers": {}},
    )

    app = _maybe_app(cfg)
    try:
        assert app.profile_var.get() == "work"
        app.profile_var.set("home")
        app._on_profile_changed(None)  # type: ignore[arg-type]
    finally:
        app.destroy()

    state = load_v2_state(cfg)
    assert state["selected_profile"] == "home"
