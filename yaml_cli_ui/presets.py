from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PRESET_SCHEMA_VERSION = 1


class PresetError(Exception):
    pass


class PresetService:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.presets_path = self._build_presets_path(config_path)
        self._state = self._load_state()

    @staticmethod
    def _build_presets_path(config_path: Path) -> Path:
        suffix = config_path.suffix
        if suffix:
            return config_path.with_suffix(f"{suffix}.presets.json")
        return Path(f"{config_path}.presets.json")

    def _default_state(self) -> dict[str, Any]:
        return {"version": PRESET_SCHEMA_VERSION, "actions": {}}

    def _load_state(self) -> dict[str, Any]:
        if not self.presets_path.exists():
            return self._default_state()
        try:
            raw = json.loads(self.presets_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self._default_state()
        if not isinstance(raw, dict):
            return self._default_state()
        actions = raw.get("actions")
        if not isinstance(actions, dict):
            return self._default_state()
        version = raw.get("version")
        if version != PRESET_SCHEMA_VERSION:
            return self._default_state()
        return raw

    def _save_state(self) -> None:
        self.presets_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.presets_path.with_suffix(f"{self.presets_path.suffix}.tmp")
        serialized = json.dumps(self._state, ensure_ascii=False, indent=2)
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(self.presets_path)

    def _action_state(self, action_id: str) -> dict[str, Any]:
        actions = self._state.setdefault("actions", {})
        if not isinstance(actions, dict):
            self._state["actions"] = {}
            actions = self._state["actions"]
        action_state = actions.setdefault(action_id, {})
        if not isinstance(action_state, dict):
            action_state = {}
            actions[action_id] = action_state
        action_state.setdefault("presets", {})
        return action_state

    def list_presets(self, action_id: str) -> list[str]:
        action_state = self._action_state(action_id)
        presets = action_state.get("presets", {})
        if not isinstance(presets, dict):
            return []
        return sorted([name for name in presets.keys() if isinstance(name, str)])

    def get_preset_values(self, action_id: str, preset_name: str) -> dict[str, Any] | None:
        action_state = self._action_state(action_id)
        presets = action_state.get("presets", {})
        if not isinstance(presets, dict):
            return None
        preset = presets.get(preset_name)
        if not isinstance(preset, dict):
            return None
        values = preset.get("values")
        return dict(values) if isinstance(values, dict) else None

    def get_last_run(self, action_id: str) -> dict[str, Any]:
        action_state = self._action_state(action_id)
        last_run = action_state.get("last_run")
        if not isinstance(last_run, dict):
            return {}
        return dict(last_run)

    def save_preset(self, action_id: str, preset_name: str, values: dict[str, Any]) -> None:
        if not preset_name.strip():
            raise PresetError("Preset name must not be empty")
        action_state = self._action_state(action_id)
        presets = action_state.setdefault("presets", {})
        if not isinstance(presets, dict):
            presets = {}
            action_state["presets"] = presets
        presets[preset_name] = {"values": dict(values)}
        self._save_state()

    def rename_preset(self, action_id: str, old_name: str, new_name: str) -> None:
        if not new_name.strip():
            raise PresetError("Preset name must not be empty")
        action_state = self._action_state(action_id)
        presets = action_state.setdefault("presets", {})
        if not isinstance(presets, dict) or old_name not in presets:
            raise PresetError("Preset was not found")
        if new_name in presets and new_name != old_name:
            raise PresetError("Preset with this name already exists")
        presets[new_name] = presets.pop(old_name)

        last_run = action_state.get("last_run")
        if isinstance(last_run, dict) and last_run.get("mode") == "preset_ref":
            if last_run.get("preset_name") == old_name:
                last_run["preset_name"] = new_name
        self._save_state()

    def delete_preset(self, action_id: str, preset_name: str) -> bool:
        action_state = self._action_state(action_id)
        presets = action_state.setdefault("presets", {})
        if not isinstance(presets, dict) or preset_name not in presets:
            return False
        del presets[preset_name]

        last_ref_cleared = False
        last_run = action_state.get("last_run")
        if isinstance(last_run, dict) and last_run.get("mode") == "preset_ref":
            if last_run.get("preset_name") == preset_name:
                action_state["last_run"] = {"mode": "snapshot", "values": {}}
                last_ref_cleared = True

        self._save_state()
        return last_ref_cleared

    def save_last_run_snapshot(self, action_id: str, values: dict[str, Any]) -> None:
        action_state = self._action_state(action_id)
        action_state["last_run"] = {"mode": "snapshot", "values": dict(values)}
        self._save_state()

    def save_last_run_preset_ref(self, action_id: str, preset_name: str) -> None:
        action_state = self._action_state(action_id)
        action_state["last_run"] = {"mode": "preset_ref", "preset_name": preset_name}
        self._save_state()

    @staticmethod
    def map_values_to_form(
        values: dict[str, Any],
        allowed_field_ids: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mapped: dict[str, Any] = {}
        unused: dict[str, Any] = {}
        for key, value in values.items():
            if key in allowed_field_ids:
                mapped[key] = value
            else:
                unused[key] = value
        return mapped, unused
