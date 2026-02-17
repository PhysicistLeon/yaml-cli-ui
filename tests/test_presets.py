from pathlib import Path

from yaml_cli_ui.presets import PresetError, PresetService


def test_presets_path_is_placed_next_to_yaml(tmp_path):
    config_path = tmp_path / "workflow.yaml"
    service = PresetService(config_path)

    assert service.presets_path == tmp_path / "workflow.yaml.presets.json"


def test_save_and_get_named_preset_roundtrip(tmp_path):
    service = PresetService(tmp_path / "demo.yaml")

    service.save_preset("build", "smoke", {"a": 1, "b": "x"})

    assert service.list_presets("build") == ["smoke"]
    assert service.get_preset_values("build", "smoke") == {"a": 1, "b": "x"}


def test_rename_updates_last_run_reference(tmp_path):
    service = PresetService(tmp_path / "demo.yaml")
    service.save_preset("build", "smoke", {"mode": "fast"})
    service.save_last_run_preset_ref("build", "smoke")

    service.rename_preset("build", "smoke", "regression")

    assert service.list_presets("build") == ["regression"]
    assert service.get_last_run("build") == {
        "mode": "preset_ref",
        "preset_name": "regression",
    }


def test_delete_referenced_preset_clears_last_run_reference(tmp_path):
    service = PresetService(tmp_path / "demo.yaml")
    service.save_preset("build", "smoke", {"mode": "fast"})
    service.save_last_run_preset_ref("build", "smoke")

    was_cleared = service.delete_preset("build", "smoke")

    assert was_cleared is True
    assert service.list_presets("build") == []
    assert service.get_last_run("build") == {"mode": "snapshot", "values": {}}


def test_delete_non_referenced_preset_keeps_last_run(tmp_path):
    service = PresetService(tmp_path / "demo.yaml")
    service.save_preset("build", "smoke", {"mode": "fast"})
    service.save_preset("build", "regression", {"mode": "slow"})
    service.save_last_run_preset_ref("build", "smoke")

    was_cleared = service.delete_preset("build", "regression")

    assert was_cleared is False
    assert service.get_last_run("build") == {"mode": "preset_ref", "preset_name": "smoke"}


def test_map_values_to_form_returns_unused_values():
    mapped, unused = PresetService.map_values_to_form(
        {"a": 1, "old": 2}, {"a", "b"}
    )

    assert mapped == {"a": 1}
    assert unused == {"old": 2}


def test_rename_validates_uniqueness(tmp_path):
    service = PresetService(tmp_path / "demo.yaml")
    service.save_preset("build", "smoke", {"x": 1})
    service.save_preset("build", "regression", {"x": 2})

    try:
        service.rename_preset("build", "smoke", "regression")
    except PresetError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected PresetError")


def test_invalid_json_recovers_to_empty_state(tmp_path):
    config_path = tmp_path / "demo.yaml"
    presets_path = Path(f"{config_path}.presets.json")
    presets_path.write_text("{broken", encoding="utf-8")

    service = PresetService(config_path)

    assert service.list_presets("build") == []
