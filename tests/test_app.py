import sys
import types

sys.modules.setdefault("yaml", types.SimpleNamespace())

from yaml_cli_ui.app import HELP_CONTENT, load_launch_settings, slider_scale_for_float_field


def test_slider_scale_for_float_step_precision():
    field = {"type": "float", "min": 0, "max": 1, "step": 0.05}
    assert slider_scale_for_float_field(field) == 100


def test_slider_scale_uses_max_decimal_places_from_numeric_props():
    field = {"type": "float", "min": 0.001, "max": 1, "default": 0.25}
    assert slider_scale_for_float_field(field) == 1000


def test_load_launch_settings_reads_default_yaml_and_browse_dir(tmp_path):
    settings_file = tmp_path / "ui.ini"
    settings_file.write_text("[ui]\ndefault_yaml = configs/main.yaml\nbrowse_dir = ./yamls\n", encoding="utf-8")

    settings = load_launch_settings(str(settings_file))

    assert settings["default_yaml"] == (tmp_path / "configs" / "main.yaml").resolve()
    assert settings["browse_dir"] == (tmp_path / "yamls").resolve()


def test_load_launch_settings_without_file_returns_defaults():
    settings = load_launch_settings(None)

    assert settings["default_yaml"] is None
    assert settings["browse_dir"] is None


def test_help_content_contains_examples_and_faq():
    assert "FAQ" in HELP_CONTENT
    assert "Минимальный пример" in HELP_CONTENT
    assert "pipeline" in HELP_CONTENT
