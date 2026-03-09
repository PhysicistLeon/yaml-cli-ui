from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .app import DEFAULT_CONFIG_PATH, load_launch_settings

if TYPE_CHECKING:
    from .app import App
    from .app_v2 import AppV2

SUPPORTED_CONFIG_VERSIONS = {1, 2}


class ConfigRoutingError(Exception):
    """Base class for bootstrap/config routing failures."""


class UnsupportedConfigVersionError(ConfigRoutingError):
    """Raised when config version is missing/invalid/unsupported."""


def _as_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def load_raw_yaml_version(path: str | Path) -> int:
    config_path = _as_path(path)
    try:
        root = yaml.compose(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigRoutingError(f"Unable to read config file: {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigRoutingError(f"Malformed YAML config: {config_path}: {exc}") from exc

    if root is None or not isinstance(root, yaml.MappingNode):
        raise UnsupportedConfigVersionError(
            f"Missing top-level mapping in config: {config_path}"
        )

    version_node = None
    for key_node, value_node in root.value:
        if key_node.value == "version":
            version_node = value_node
            break

    if version_node is None:
        raise UnsupportedConfigVersionError(
            f"Missing required top-level 'version' in config: {config_path}"
        )

    try:
        version = int(version_node.value)
    except (TypeError, ValueError) as exc:
        raise UnsupportedConfigVersionError(
            f"Invalid non-integer config version in {config_path}: {version_node.value!r}"
        ) from exc

    return version


def detect_yaml_version(path: str | Path) -> int:
    version = load_raw_yaml_version(path)
    if version not in SUPPORTED_CONFIG_VERSIONS:
        raise UnsupportedConfigVersionError(
            f"Unsupported config version {version} in {Path(path)}; supported versions: 1, 2"
        )
    return version


def select_app_class_for_version(version: int) -> type[object]:
    from .app import App
    from .app_v2 import AppV2

    if version == 1:
        return App
    if version == 2:
        return AppV2
    raise UnsupportedConfigVersionError(
        f"Unsupported config version {version}; supported versions: 1, 2"
    )


def open_app_for_config(
    path: str | Path,
    *,
    settings_path: str | Path | None = None,
    root: Any | None = None,
    browse_dir: str | Path | None = None,
) -> object:
    from .app import App
    from .app_v2 import AppV2

    del root  # Reserved for future tiny glue if embedding root is needed.

    config_path = _as_path(path)
    version = detect_yaml_version(config_path)
    app_class = select_app_class_for_version(version)

    resolved_browse_dir = browse_dir
    if resolved_browse_dir is None and settings_path is not None:
        settings = load_launch_settings(str(settings_path))
        resolved_browse_dir = settings.get("browse_dir")

    if app_class is App:
        return App(str(config_path), browse_dir=resolved_browse_dir)
    if app_class is AppV2:
        return AppV2(str(config_path))
    raise UnsupportedConfigVersionError(
        f"Unsupported config version {version}; supported versions: 1, 2"
    )


def resolve_launch_config(
    cli_config: str | None,
    *,
    settings_path: str | None,
) -> tuple[Path, Path | None]:
    settings = load_launch_settings(settings_path)
    default_config = settings["default_yaml"] or Path(DEFAULT_CONFIG_PATH)
    config_path = Path(cli_config).expanduser() if cli_config else Path(default_config)
    browse_dir = settings["browse_dir"]
    return config_path.resolve(), browse_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML-driven CLI UI")
    parser.add_argument("config", nargs="?", default=None)
    parser.add_argument(
        "--settings",
        help="Path to INI file with [ui] default_yaml and browse_dir.",
        default="app.ini",
    )
    args = parser.parse_args()

    config_path, browse_dir = resolve_launch_config(
        args.config,
        settings_path=args.settings,
    )
    app = open_app_for_config(
        config_path,
        settings_path=args.settings,
        browse_dir=browse_dir,
    )
    app.mainloop()
