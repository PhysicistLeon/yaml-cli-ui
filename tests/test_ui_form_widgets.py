from yaml_cli_ui.ui.form_widgets import (
    FormField,
    _display_fixed_value,
    apply_values_to_v2_form,
    collect_v2_form_values,
)
from yaml_cli_ui.v2.models import ParamDef, ParamType, SecretSource


class Entry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_):
        self.value = ""

    def insert(self, *_args):
        self.value = _args[-1]


class Text:
    def __init__(self, value=""):
        self.value = value

    def get(self, *_):
        return self.value

    def delete(self, *_):
        self.value = ""

    def insert(self, *_args):
        self.value = _args[-1]


class BoolVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class BoolWidget:
    def __init__(self, value):
        self.var = BoolVar(value)


class Multi:
    def __init__(self):
        self.options = ["a", "b", "c"]
        self.selected = {1}

    def curselection(self):
        return list(self.selected)

    def get(self, i):
        return self.options[i]

    def size(self):
        return len(self.options)

    def selection_clear(self, *_):
        self.selected.clear()

    def selection_set(self, i):
        self.selected.add(i)


def test_collect_values_and_required_validation(monkeypatch, tmp_path):
    file_path = tmp_path / "x.txt"
    file_path.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("MY_SECRET", "env-secret")

    fields = {
        "name": FormField("name", ParamDef(type=ParamType.STRING, required=True), Entry("demo")),
        "count": FormField("count", ParamDef(type=ParamType.INT), Entry("5")),
        "flag": FormField("flag", ParamDef(type=ParamType.BOOL), BoolWidget(True)),
        "multi": FormField("multi", ParamDef(type=ParamType.MULTICHOICE), Multi()),
        "path": FormField(
            "path",
            ParamDef(type=ParamType.FILEPATH, must_exist=True),
            type("PathW", (), {"entry": Entry(str(file_path))})(),
        ),
        "token": FormField(
            "token",
            ParamDef(type=ParamType.SECRET, required=True, source=SecretSource.ENV, env="MY_SECRET"),
            Entry("ignored"),
        ),
    }

    values, errors = collect_v2_form_values(fields)

    assert not errors
    assert values["count"] == 5
    assert values["flag"] is True
    assert values["multi"] == ["b"]
    assert values["token"] == "env-secret"


def test_collect_values_reports_path_and_list_and_required_errors(tmp_path):
    fields = {
        "missing": FormField(
            "missing",
            ParamDef(type=ParamType.FILEPATH, must_exist=True, required=True),
            type("PathW", (), {"entry": Entry(str(tmp_path / "none.txt"))})(),
        ),
        "pairs": FormField("pairs", ParamDef(type=ParamType.KV_LIST), Text("{k: v}")),
        "items": FormField("items", ParamDef(type=ParamType.STRUCT_LIST), Text("name: x")),
        "name": FormField("name", ParamDef(type=ParamType.STRING, required=True), Entry("")),
    }

    _values, errors = collect_v2_form_values(fields)

    assert "missing path does not exist" in errors
    assert "pairs: must be a list" in errors
    assert "items: must be a list" in errors
    assert "name is required" in errors


def test_collect_values_reports_numeric_parse_errors():
    fields = {
        "i": FormField("i", ParamDef(type=ParamType.INT), Entry("abc")),
        "f": FormField("f", ParamDef(type=ParamType.FLOAT), Entry("x.y")),
    }

    _values, errors = collect_v2_form_values(fields)

    assert "i: must be an integer" in errors
    assert "f: must be a float" in errors


def test_masked_fixed_secret_display():
    assert _display_fixed_value(ParamDef(type=ParamType.SECRET), "plaintext") == "******"


def test_apply_values_updates_widgets():
    multi = Multi()
    fields = {
        "name": FormField("name", ParamDef(type=ParamType.STRING), Entry("")),
        "notes": FormField("notes", ParamDef(type=ParamType.TEXT), Text("")),
        "flag": FormField("flag", ParamDef(type=ParamType.BOOL), BoolWidget(False)),
        "multi": FormField("multi", ParamDef(type=ParamType.MULTICHOICE), multi),
    }

    apply_values_to_v2_form(fields, {"name": "abc", "notes": "tt", "flag": True, "multi": ["a", "c"]})

    assert fields["name"].widget.get() == "abc"
    assert fields["notes"].widget.get("1.0", "end") == "tt"
    assert fields["flag"].widget.var.get() is True
    assert multi.selected == {0, 2}
