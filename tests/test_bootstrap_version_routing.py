from __future__ import annotations

from pathlib import Path

import pytest

from yaml_cli_ui.bootstrap import (
    ConfigRoutingError,
    UnsupportedConfigVersionError,
    detect_yaml_version,
    open_app_for_config,
    resolve_launch_config,
    select_app_class_for_version,
)
from yaml_cli_ui.app import App
from yaml_cli_ui.app_v2 import AppV2


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_detect_yaml_version_v1(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "v1.yaml", "version: 1\nactions: {}\n")
    assert detect_yaml_version(cfg) == 1


def test_detect_yaml_version_v2(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "v2.yaml", "version: 2\ncommands: {}\nlaunchers: {}\n")
    assert detect_yaml_version(cfg) == 2


def test_detect_yaml_version_missing_version(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "missing.yaml", "actions: {}\n")

    with pytest.raises(UnsupportedConfigVersionError) as exc:
        detect_yaml_version(cfg)

    assert str(cfg.resolve()) in str(exc.value)


def test_detect_yaml_version_unsupported(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "v3.yaml", "version: 3\n")

    with pytest.raises(UnsupportedConfigVersionError) as exc:
        detect_yaml_version(cfg)

    assert "supported versions: 1, 2" in str(exc.value)


def test_detect_yaml_version_invalid_type(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "bad.yaml", "version: nope\n")

    with pytest.raises(UnsupportedConfigVersionError):
        detect_yaml_version(cfg)


def test_detect_yaml_version_malformed_yaml(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "broken.yaml", "version: [\n")

    with pytest.raises(ConfigRoutingError):
        detect_yaml_version(cfg)


def test_select_app_class_for_version():
    assert select_app_class_for_version(1) is App
    assert select_app_class_for_version(2) is AppV2


def test_open_app_for_config_routes_v1(tmp_path: Path, monkeypatch):
    cfg = _write_yaml(tmp_path / "v1.yaml", "version: 1\nactions: {}\n")
    calls: list[tuple[str, tuple, dict]] = []

    class DummyV1:
        def __init__(self, *args, **kwargs):
            calls.append(("v1", args, kwargs))

    class DummyV2:
        def __init__(self, *args, **kwargs):
            calls.append(("v2", args, kwargs))

    monkeypatch.setattr("yaml_cli_ui.bootstrap.App", DummyV1)
    monkeypatch.setattr("yaml_cli_ui.bootstrap.AppV2", DummyV2)

    open_app_for_config(cfg, browse_dir=tmp_path)

    assert calls and calls[0][0] == "v1"
    assert calls[0][1][0] == str(cfg.resolve())


def test_open_app_for_config_routes_v2(tmp_path: Path, monkeypatch):
    cfg = _write_yaml(
        tmp_path / "v2.yaml",
        "version: 2\ncommands: {}\nlaunchers: {}\n",
    )
    calls: list[tuple[str, tuple, dict]] = []

    class DummyV1:
        def __init__(self, *args, **kwargs):
            calls.append(("v1", args, kwargs))

    class DummyV2:
        def __init__(self, *args, **kwargs):
            calls.append(("v2", args, kwargs))

    monkeypatch.setattr("yaml_cli_ui.bootstrap.App", DummyV1)
    monkeypatch.setattr("yaml_cli_ui.bootstrap.AppV2", DummyV2)

    open_app_for_config(cfg)

    assert calls == [("v2", (str(cfg.resolve()),), {})]


def test_resolve_launch_config_uses_settings_default_yaml(tmp_path: Path):
    v1_cfg = _write_yaml(tmp_path / "from_settings.yaml", "version: 1\nactions: {}\n")
    ini = tmp_path / "app.ini"
    ini.write_text(
        f"[ui]\ndefault_yaml = {v1_cfg.name}\nbrowse_dir = .\n",
        encoding="utf-8",
    )

    config_path, browse_dir = resolve_launch_config(None, settings_path=str(ini))

    assert config_path == v1_cfg.resolve()
    assert browse_dir == tmp_path.resolve()


def test_resolve_launch_config_cli_arg_overrides_settings(tmp_path: Path):
    default_cfg = _write_yaml(tmp_path / "default.yaml", "version: 1\nactions: {}\n")
    cli_cfg = _write_yaml(
        tmp_path / "cli.yaml",
        "version: 2\ncommands: {}\nlaunchers: {}\n",
    )
    ini = tmp_path / "app.ini"
    ini.write_text(f"[ui]\ndefault_yaml = {default_cfg.name}\n", encoding="utf-8")

    config_path, _ = resolve_launch_config(str(cli_cfg), settings_path=str(ini))

    assert config_path == cli_cfg.resolve()
