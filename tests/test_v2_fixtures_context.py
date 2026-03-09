import pytest

from v2_test_utils import load_fixture_doc
from yaml_cli_ui.v2.context import build_runtime_context, resolve_selected_profile
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.models import ProfileDef, V2Document


def test_locals_are_evaluated_sequentially():
    doc = load_fixture_doc("valid_locals.yaml")
    ctx = build_runtime_context(doc, params={"collection": "weekly"}, selected_profile_name="home")

    assert ctx.locals["run_root"] == "/work/runs/weekly"
    assert ctx.locals["spool_dir"] == "/work/runs/weekly/spool"
    assert ctx.locals["urls_file"] == "/work/runs/weekly/spool/urls.json"


def test_imported_locals_and_root_local_using_imported_values():
    doc = load_fixture_doc("valid_locals.yaml")
    ctx = build_runtime_context(doc, params={"collection": "x"}, selected_profile_name="home")

    assert ctx.imported["media"]["scrape_script"] == "scripts/scrape.py"
    assert ctx.imported["fs"]["ensure_dir_script"] == "scripts/ensure_dir.py"
    assert ctx.locals["media_script"] == "scripts/scrape.py"


def test_with_values_override_short_name_only():
    doc = V2Document()
    ctx = build_runtime_context(doc, params={"x": "param"}, with_values={"x": "binding"})
    rendered = ctx.as_mapping()

    assert rendered["bindings"]["x"] == "binding"
    assert rendered["params"]["x"] == "param"


def test_profile_selection_rules():
    assert resolve_selected_profile(V2Document()) == {}

    one = V2Document(profiles={"p": ProfileDef(workdir="/a")})
    assert resolve_selected_profile(one)["workdir"] == "/a"

    many = V2Document(profiles={"a": ProfileDef(), "b": ProfileDef()})
    with pytest.raises(V2ExecutionError, match="multiple profiles"):
        resolve_selected_profile(many)

    assert resolve_selected_profile(many, selected_profile_name="b") == {"workdir": None, "env": {}, "runtimes": {}}
