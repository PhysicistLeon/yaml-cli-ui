import tkinter as tk

import pytest

from yaml_cli_ui.ui.form_widgets import (
    FormField,
    _display_fixed_value,
    apply_values_to_v2_form,
    collect_v2_form_values,
    LONG_ENTRY_WIDTH,
    create_v2_form_fields,
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


def test_path_entry_expands_with_grid_contract():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {"out": ParamDef(type=ParamType.FILEPATH)},
            initial_values={"out": "/tmp/a/very/long/path/value.npy"},
        )

        frame = fields["out"].widget
        entry = frame.entry
        frame_grid = frame.grid_info()
        entry_grid = entry.grid_info()

        assert int(body.grid_columnconfigure(1)["weight"]) == 1
        assert frame_grid["sticky"] == "ew"
        assert entry_grid["sticky"] == "ew"
        assert int(entry.cget("width")) >= LONG_ENTRY_WIDTH
    finally:
        root.destroy()


def test_fixed_entry_uses_wide_layout_contract():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {"f": ParamDef(type=ParamType.FILEPATH)},
            fixed_values={"f": "/tmp/very/long/fixed/output/file.npy"},
        )
        widget = fields["f"].widget
        assert int(widget.cget("width")) >= LONG_ENTRY_WIDTH
        assert widget.cget("state") == "disabled"
        assert widget.grid_info()["sticky"] == "ew"
    finally:
        root.destroy()


def test_int_slider_widget_collect_and_apply_roundtrip():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {
                "fps": ParamDef(type=ParamType.INT, default=20, min=1, max=60, step=1, widget="slider"),
            },
        )

        slider_widget = fields["fps"].widget
        assert hasattr(slider_widget, "slider_var")
        assert int(slider_widget.slider_var.get()) == 20

        apply_values_to_v2_form(fields, {"fps": 31})
        values, errors = collect_v2_form_values(fields)
        assert not errors
        assert values["fps"] == 31
    finally:
        root.destroy()


def test_int_slider_clamps_and_snaps_on_init_and_apply():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {
                "n": ParamDef(type=ParamType.INT, min=1, max=10, step=3, widget="slider"),
            },
            initial_values={"n": -100},
        )
        widget = fields["n"].widget
        assert int(widget.slider_var.get()) == 1

        apply_values_to_v2_form(fields, {"n": 9})
        values, errors = collect_v2_form_values(fields)
        assert not errors
        # snapped to nearest step starting from min: 1,4,7,10
        assert values["n"] == 10
    finally:
        root.destroy()


def test_float_slider_auto_enabled_by_min_max_and_precision_from_step():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {
                "ratio": ParamDef(type=ParamType.FLOAT, min=0.0, max=1.0, step=0.05),
            },
            initial_values={"ratio": 0.333333},
        )
        widget = fields["ratio"].widget
        assert hasattr(widget, "slider_var")
        assert widget.value_label.cget("text") == "0.35"

        apply_values_to_v2_form(fields, {"ratio": 1.2})
        values, errors = collect_v2_form_values(fields)
        assert not errors
        assert values["ratio"] == pytest.approx(1.0)
        assert widget.value_label.cget("text") == "1"
    finally:
        root.destroy()


def test_numeric_param_with_non_slider_widget_does_not_auto_enable_slider():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in environment: {exc}")
    root.withdraw()
    try:
        body = tk.Frame(root)
        body.grid()
        fields = create_v2_form_fields(
            body,
            {
                "n": ParamDef(type=ParamType.INT, min=0, max=10, widget="input"),
            },
        )
        assert not hasattr(fields["n"].widget, "slider_var")
    finally:
        root.destroy()
