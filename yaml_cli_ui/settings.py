from __future__ import annotations

import configparser
from pathlib import Path


def _resolve_ini_path(value: str, ini_path: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = (ini_path.parent / candidate).resolve()
    return candidate


def load_launch_settings(ini_path: str | None) -> dict[str, Path | None]:
    settings: dict[str, Path | None] = {"default_yaml": None, "browse_dir": None}
    if not ini_path:
        return settings

    config = configparser.ConfigParser()
    parsed = config.read(ini_path, encoding="utf-8")
    if not parsed:
        raise FileNotFoundError(f"Settings file was not found: {ini_path}")

    resolved_ini_path = Path(parsed[0]).resolve()
    ui_section = config["ui"] if config.has_section("ui") else {}

    default_yaml = str(ui_section.get("default_yaml", "")).strip()
    if default_yaml:
        settings["default_yaml"] = _resolve_ini_path(default_yaml, resolved_ini_path)

    browse_dir = str(ui_section.get("browse_dir", "")).strip()
    if browse_dir:
        settings["browse_dir"] = _resolve_ini_path(browse_dir, resolved_ini_path)

    return settings
