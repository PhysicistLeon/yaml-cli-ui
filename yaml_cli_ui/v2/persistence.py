"""Persistence for YAML CLI UI v2 launcher presets/state.

EBNF (minimal):

V2PresetFile :=
{
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

V2StateFile :=
{
  "version": 2,
  ["selected_profile": string | null],
  "launchers": {
    launcher_name: {
      "last_values": ParamValueMap,
      ["last_selected_preset": string | null]
    }
  }
}

ParamValueMap := map of param_id -> stored_value, excluding secret params.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .models import ParamType, V2Document

V2_STORAGE_VERSION = 2


class V2PersistenceError(RuntimeError):
    """Persistence load/save error for v2 presets/state files."""


def get_v2_presets_path(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser()
    return path.with_name(f"{path.name}.launchers.presets.json")


def get_v2_state_path(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser()
    return path.with_name(f"{path.name}.state.json")


def _default_presets_payload() -> dict[str, Any]:
    return {"version": V2_STORAGE_VERSION, "launchers": {}}


def _default_state_payload() -> dict[str, Any]:
    return {"version": V2_STORAGE_VERSION, "selected_profile": None, "launchers": {}}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise V2PersistenceError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise V2PersistenceError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise V2PersistenceError(f"Invalid JSON root in {path}: object required")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except OSError as exc:
        raise V2PersistenceError(f"Cannot write {path}: {exc}") from exc
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _expect_mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise V2PersistenceError(f"Invalid storage format: '{what}' must be an object")
    return value


def _validate_presets_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("version") != V2_STORAGE_VERSION:
        raise V2PersistenceError(
            f"Unsupported v2 persistence version: {payload.get('version')!r}"
        )
    launchers = _expect_mapping(payload.get("launchers"), "launchers")
    for launcher_name, launcher_payload in launchers.items():
        launcher_map = _expect_mapping(launcher_payload, f"launchers.{launcher_name}")
        presets = launcher_map.get("presets")
        if presets is None:
            continue
        presets_map = _expect_mapping(presets, f"launchers.{launcher_name}.presets")
        for preset_name, preset_payload in presets_map.items():
            preset_map = _expect_mapping(
                preset_payload, f"launchers.{launcher_name}.presets.{preset_name}"
            )
            if "params" in preset_map:
                _expect_mapping(
                    preset_map.get("params"),
                    f"launchers.{launcher_name}.presets.{preset_name}.params",
                )


def _validate_state_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("version") != V2_STORAGE_VERSION:
        raise V2PersistenceError(
            f"Unsupported v2 persistence version: {payload.get('version')!r}"
        )
    selected_profile = payload.get("selected_profile")
    if selected_profile is not None and not isinstance(selected_profile, str):
        raise V2PersistenceError("Invalid storage format: 'selected_profile' must be string|null")

    launchers = _expect_mapping(payload.get("launchers"), "launchers")
    for launcher_name, launcher_payload in launchers.items():
        launcher_map = _expect_mapping(launcher_payload, f"launchers.{launcher_name}")
        if "last_values" in launcher_map:
            _expect_mapping(launcher_map.get("last_values"), f"launchers.{launcher_name}.last_values")
        if "last_selected_preset" in launcher_map:
            selected_preset = launcher_map.get("last_selected_preset")
            if selected_preset is not None and not isinstance(selected_preset, str):
                raise V2PersistenceError(
                    "Invalid storage format: "
                    f"'launchers.{launcher_name}.last_selected_preset' must be string|null"
                )


def load_v2_presets(config_path: str | Path) -> dict[str, Any]:
    path = get_v2_presets_path(config_path)
    if not path.exists():
        return _default_presets_payload()
    payload = _read_json(path)
    _validate_presets_payload(payload)
    return payload


def save_v2_presets(config_path: str | Path, data: Mapping[str, Any]) -> None:
    payload = dict(data)
    _validate_presets_payload(payload)
    _atomic_write_json(get_v2_presets_path(config_path), payload)


def load_v2_state(config_path: str | Path) -> dict[str, Any]:
    path = get_v2_state_path(config_path)
    if not path.exists():
        return _default_state_payload()
    payload = _read_json(path)
    _validate_state_payload(payload)
    return payload


def save_v2_state(config_path: str | Path, data: Mapping[str, Any]) -> None:
    payload = dict(data)
    _validate_state_payload(payload)
    _atomic_write_json(get_v2_state_path(config_path), payload)


def sanitize_param_values_for_storage(
    doc: V2Document,
    launcher_name: str,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Sanitize values for persistence.

    Policy:
    - strip secret params always;
    - strip launcher.with-bound params from persisted editable values.
    """

    launcher = doc.launchers[launcher_name]
    sanitized: dict[str, Any] = {}
    for key, value in values.items():
        param = doc.params.get(key)
        if param is None:
            continue
        if param.type == ParamType.SECRET:
            continue
        if key in launcher.with_values:
            continue
        sanitized[key] = value
    return sanitized


class LauncherPersistenceService:
    """Thin stateful API around v2 launcher presets/state files."""

    def __init__(self, config_path: str | Path, doc: V2Document):
        self.config_path = Path(config_path).expanduser()
        self.doc = doc
        self.warnings: list[str] = []
        self._presets = _default_presets_payload()
        self._state = _default_state_payload()

    @property
    def last_warning(self) -> str | None:
        """Backward-compatible convenience alias for last warning."""

        return self.warnings[-1] if self.warnings else None

    def _record_warning(self, message: str) -> None:
        self.warnings.append(message)

    def _filter_editable_values(self, launcher_name: str, values: Mapping[str, Any]) -> dict[str, Any]:
        allowed = set(self.doc.params.keys())
        allowed -= set(self.doc.launchers[launcher_name].with_values.keys())
        filtered: dict[str, Any] = {}
        for key, value in values.items():
            if key not in allowed:
                continue
            if self.doc.params[key].type == ParamType.SECRET:
                continue
            filtered[key] = value
        return filtered

    def load_presets(self) -> dict[str, Any]:
        try:
            self._presets = load_v2_presets(self.config_path)
        except V2PersistenceError as exc:
            self._record_warning(str(exc))
            self._presets = _default_presets_payload()
        return self._presets

    def save_presets(self) -> None:
        save_v2_presets(self.config_path, self._presets)

    def load_state(self) -> dict[str, Any]:
        try:
            self._state = load_v2_state(self.config_path)
        except V2PersistenceError as exc:
            self._record_warning(str(exc))
            self._state = _default_state_payload()
        return self._state

    def save_state(self) -> None:
        save_v2_state(self.config_path, self._state)

    def _ensure_launcher_presets(self, launcher_name: str) -> dict[str, Any]:
        launchers = self._presets.setdefault("launchers", {})
        launcher = launchers.setdefault(launcher_name, {})
        return launcher.setdefault("presets", {})

    def _ensure_launcher_state(self, launcher_name: str) -> dict[str, Any]:
        launchers = self._state.setdefault("launchers", {})
        return launchers.setdefault(launcher_name, {"last_values": {}, "last_selected_preset": None})

    def list_presets(self, launcher_name: str) -> list[str]:
        presets = self._ensure_launcher_presets(launcher_name)
        return sorted(presets.keys())

    def get_preset(self, launcher_name: str, preset_name: str) -> dict[str, Any] | None:
        presets = self._ensure_launcher_presets(launcher_name)
        preset = presets.get(preset_name)
        if not isinstance(preset, dict):
            return None
        params = preset.get("params")
        if not isinstance(params, dict):
            return None
        return {"params": self._filter_editable_values(launcher_name, params)}

    def upsert_preset(
        self,
        launcher_name: str,
        preset_name: str,
        params: Mapping[str, Any],
    ) -> None:
        presets = self._ensure_launcher_presets(launcher_name)
        sanitized = sanitize_param_values_for_storage(self.doc, launcher_name, params)
        presets[preset_name] = {"params": sanitized}
        self.save_presets()

    def delete_preset(self, launcher_name: str, preset_name: str) -> None:
        presets = self._ensure_launcher_presets(launcher_name)
        presets.pop(preset_name, None)
        self.save_presets()

    def rename_preset(self, launcher_name: str, old_name: str, new_name: str) -> None:
        presets = self._ensure_launcher_presets(launcher_name)
        if old_name not in presets:
            return
        presets[new_name] = presets.pop(old_name)
        self.save_presets()

    def apply_preset_values(self, launcher_name: str, preset_name: str) -> dict[str, Any]:
        preset = self.get_preset(launcher_name, preset_name)
        if not preset:
            return {}
        return self._filter_editable_values(launcher_name, preset["params"])

    def get_last_values(self, launcher_name: str) -> dict[str, Any]:
        launcher_state = self._ensure_launcher_state(launcher_name)
        values = launcher_state.get("last_values")
        if not isinstance(values, dict):
            return {}
        return self._filter_editable_values(launcher_name, values)

    def apply_known_editable_values(
        self,
        launcher_name: str,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._filter_editable_values(launcher_name, values)

    def set_last_values(self, launcher_name: str, params: Mapping[str, Any]) -> None:
        launcher_state = self._ensure_launcher_state(launcher_name)
        launcher_state["last_values"] = sanitize_param_values_for_storage(self.doc, launcher_name, params)
        self.save_state()

    def get_last_selected_preset(self, launcher_name: str) -> str | None:
        launcher_state = self._ensure_launcher_state(launcher_name)
        value = launcher_state.get("last_selected_preset")
        return value if isinstance(value, str) else None

    def set_last_selected_preset(self, launcher_name: str, preset_name: str | None) -> None:
        launcher_state = self._ensure_launcher_state(launcher_name)
        launcher_state["last_selected_preset"] = preset_name
        self.save_state()

    def get_selected_profile(self) -> str | None:
        profile = self._state.get("selected_profile")
        return profile if isinstance(profile, str) else None

    def set_selected_profile(self, profile_name: str | None) -> None:
        self._state["selected_profile"] = profile_name
        self.save_state()


__all__ = [
    "LauncherPersistenceService",
    "V2PersistenceError",
    "get_v2_presets_path",
    "get_v2_state_path",
    "load_v2_presets",
    "save_v2_presets",
    "load_v2_state",
    "save_v2_state",
    "sanitize_param_values_for_storage",
]
