import sys
import types

sys.modules.setdefault("yaml", types.SimpleNamespace())

from yaml_cli_ui.app import slider_scale_for_float_field


def test_slider_scale_for_float_step_precision():
    field = {"type": "float", "min": 0, "max": 1, "step": 0.05}
    assert slider_scale_for_float_field(field) == 100


def test_slider_scale_uses_max_decimal_places_from_numeric_props():
    field = {"type": "float", "min": 0.001, "max": 1, "default": 0.25}
    assert slider_scale_for_float_field(field) == 1000
