import pytest

from yaml_cli_ui.ui.form_widgets import FormValidationError, ParamForm, _display_fixed_value
from yaml_cli_ui.v2.models import ParamDef, ParamType, SecretSource


class _Entry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Text:
    def __init__(self, value):
        self.value = value

    def get(self, *_args):
        return self.value


class _BoolVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _Bool:
    def __init__(self, value):
        self.var = _BoolVar(value)


def test_collect_form_handles_required_and_fixed_values():
    form = ParamForm.__new__(ParamForm)
    form.fixed_values = {"mode": "fixed"}
    form.fields = {
        "name": (ParamDef(type=ParamType.STRING, required=True), _Entry("demo")),
        "enabled": (ParamDef(type=ParamType.BOOL), _Bool(True)),
        "count": (ParamDef(type=ParamType.INT), _Entry("5")),
        "notes": (ParamDef(type=ParamType.TEXT), _Text("n")),
    }

    data = ParamForm.collect(form)

    assert data == {"mode": "fixed", "name": "demo", "enabled": True, "count": 5, "notes": "n"}


def test_collect_form_required_validation_error():
    form = ParamForm.__new__(ParamForm)
    form.fixed_values = {}
    form.fields = {"name": (ParamDef(type=ParamType.STRING, required=True), _Entry(""))}

    with pytest.raises(FormValidationError):
        ParamForm.collect(form)


def test_display_fixed_secret_masking():
    env_param = ParamDef(type=ParamType.SECRET, source=SecretSource.ENV, env="TOKEN")
    plain_param = ParamDef(type=ParamType.SECRET)

    assert _display_fixed_value(env_param, "abc") == "<env:TOKEN>"
    assert _display_fixed_value(plain_param, "abc") == "******"
