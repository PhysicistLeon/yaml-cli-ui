"""Persistence helpers for YAML CLI UI v2 launchers.

EBNF-like shapes
----------------
V2PresetFile := {
  "version": 2,
  "launchers": {
    launcher_name: {
      "presets": {
        preset_name: {
          "params": ParamValueMap
        }
      }
    }
  }
}

V2StateFile := {
  "version": 2,
  ["selected_profile": string | null],
  "launchers": {
    launcher_name: {
      "last_values": ParamValueMap,
      ["last_selected_preset": string | null]
    }
  }
}

ParamValueMap := map[param_id -> stored_value] excluding secret params.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .models import ParamType, V2Document

V2_STORAGE_VERSION = 2


class V2PersistenceError(Exception):
    """Raised when v2 persistence files are malformed or cannot be processed."""


def get_v2_presets_path(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser().resolve()
    return Path(f"{path}.launchers.presets.json")


def get_v2_state_path(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser().resolve()
    return Path(f"{path}.state.json")


def _default_presets() -> dict[str, Any]:
    return {"version": V2_STORAGE_VERSION, "launchers": {}}


def _default_state() -> dict[str, Any]:
    return {"version": V2_STORAGE_VERSION, "launchers": {}}


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise V2PersistenceError(f"Broken JSON in file: {path}") from exc
    if not isinstance(payload, dict):
        raise V2PersistenceError(f"Top-level JSON must be object in file: {path}")
    return payload


def _validate_presets(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    if payload.get("version") != V2_STORAGE_VERSION:
        raise V2PersistenceError(f"Unsupported presets version in file: {path}")
    launchers = payload.get("launchers", {})
    if not isinstance(launchers, dict):
        raise V2PersistenceError(f"'launchers' must be an object in file: {path}")
    return {"version": V2_STORAGE_VERSION, "launchers": launchers}


def _validate_state(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    if payload.get("version") != V2_STORAGE_VERSION:
        raise V2PersistenceError(f"Unsupported state version in file: {path}")
    launchers = payload.get("launchers", {})
    if not isinstance(launchers, dict):
        raise V2PersistenceError(f"'launchers' must be an object in file: {path}")
    selected_profile = payload.get("selected_profile")
    if selected_profile is not None and not isinstance(selected_profile, str):
        raise V2PersistenceError(f"'selected_profile' must be string|null in file: {path}")
    data: dict[str, Any] = {"version": V2_STORAGE_VERSION, "launchers": launchers}
    if "selected_profile" in payload:
        data["selected_profile"] = selected_profile
    return data


def load_v2_presets(config_path: str | Path) -> dict[str, Any]:
    path = get_v2_presets_path(config_path)
    if not path.exists():
        return _default_presets()
    return _validate_presets(_read_json_file(path), path)


def load_v2_state(config_path: str | Path) -> dict[str, Any]:
    path = get_v2_state_path(config_path)
    if not path.exists():
        return _default_state()
    return _validate_state(_read_json_file(path), path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise V2PersistenceError(f"Failed to write file: {path}") from exc


def save_v2_presets(config_path: str | Path, data: Mapping[str, Any]) -> None:
    payload = dict(data)
    payload["version"] = V2_STORAGE_VERSION
    payload.setdefault("launchers", {})
    _atomic_write_json(get_v2_presets_path(config_path), payload)


def save_v2_state(config_path: str | Path, data: Mapping[str, Any]) -> None:
    payload = dict(data)
    payload["version"] = V2_STORAGE_VERSION
    payload.setdefault("launchers", {})
    _atomic_write_json(get_v2_state_path(config_path), payload)


def sanitize_param_values_for_storage(
    doc: V2Document,
    launcher_name: str,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Sanitize values for storage.

    Policy: store only editable root params (exclude launcher.with bindings)
    and remove all params declared as `secret`.
    """

    launcher = doc.launchers[launcher_name]
    fixed_keys = set(launcher.with_values)
    out: dict[str, Any] = {}
    for name, value in values.items():
        param = doc.params.get(name)
        if param is None:
            continue
        if name in fixed_keys:
            continue
        if param.type == ParamType.SECRET:
            continue
        out[name] = value
    return out


class LauncherPersistenceService:
    def __init__(self, config_path: str | Path, doc: V2Document, *, tolerate_errors: bool = True):
        self.config_path = Path(config_path).expanduser().resolve()
        self.doc = doc
        self.tolerate_errors = tolerate_errors
        self.warnings: list[str] = []
        self._presets = self._load_or_default(load_v2_presets, _default_presets)
        self._state = self._load_or_default(load_v2_state, _default_state)

    def _load_or_default(self, loader, default_factory):
        try:
            return loader(self.config_path)
        except V2PersistenceError as exc:
            if not self.tolerate_errors:
                raise
            self.warnings.append(str(exc))
            return default_factory()

    def load_presets(self) -> dict[str, Any]:
        return self._presets

    def save_presets(self) -> None:
        save_v2_presets(self.config_path, self._presets)

    def load_state(self) -> dict[str, Any]:
        return self._state

    def save_state(self) -> None:
        save_v2_state(self.config_path, self._state)

    def list_presets(self, launcher_name: str) -> list[str]:
        presets = self._presets.get("launchers", {}).get(launcher_name, {}).get("presets", {})
        if not isinstance(presets, dict):
            return []
        return sorted(presets)

    def get_preset(self, launcher_name: str, preset_name: str) -> dict[str, Any] | None:
        preset = (
            self._presets.get("launchers", {})
            .get(launcher_name, {})
            .get("presets", {})
            .get(preset_name)
        )
        if not isinstance(preset, dict):
            return None
        params = preset.get("params", {})
        if not isinstance(params, dict):
            return None
        return sanitize_param_values_for_storage(self.doc, launcher_name, params)

    def upsert_preset(self, launcher_name: str, preset_name: str, params: Mapping[str, Any]) -> None:
        clean = sanitize_param_values_for_storage(self.doc, launcher_name, params)
        launchers = self._presets.setdefault("launchers", {})
        launcher_slot = launchers.setdefault(launcher_name, {})
        presets = launcher_slot.setdefault("presets", {})
        presets[preset_name] = {"params": clean}
        self.save_presets()

    def delete_preset(self, launcher_name: str, preset_name: str) -> None:
        presets = self._presets.get("launchers", {}).get(launcher_name, {}).get("presets", {})
        if isinstance(presets, dict):
            presets.pop(preset_name, None)
            self.save_presets()

    def rename_preset(self, launcher_name: str, old_name: str, new_name: str) -> None:
        presets = self._presets.get("launchers", {}).get(launcher_name, {}).get("presets", {})
        if not isinstance(presets, dict) or old_name not in presets:
            return
        presets[new_name] = presets.pop(old_name)
        self.save_presets()

    def get_last_values(self, launcher_name: str) -> dict[str, Any]:
        values = self._state.get("launchers", {}).get(launcher_name, {}).get("last_values", {})
        if not isinstance(values, dict):
            return {}
        return sanitize_param_values_for_storage(self.doc, launcher_name, values)

    def set_last_values(self, launcher_name: str, params: Mapping[str, Any]) -> None:
        clean = sanitize_param_values_for_storage(self.doc, launcher_name, params)
        launchers = self._state.setdefault("launchers", {})
        slot = launchers.setdefault(launcher_name, {})
        slot["last_values"] = clean
        self.save_state()

    def get_last_selected_preset(self, launcher_name: str) -> str | None:
        value = self._state.get("launchers", {}).get(launcher_name, {}).get("last_selected_preset")
        return value if isinstance(value, str) else None

    def set_last_selected_preset(self, launcher_name: str, preset_name: str | None) -> None:
        launchers = self._state.setdefault("launchers", {})
        slot = launchers.setdefault(launcher_name, {})
        slot["last_selected_preset"] = preset_name
        self.save_state()

    def get_selected_profile(self) -> str | None:
        value = self._state.get("selected_profile")
        return value if isinstance(value, str) else None

    def set_selected_profile(self, profile_name: str | None) -> None:
        self._state["selected_profile"] = profile_name
        self.save_state()
