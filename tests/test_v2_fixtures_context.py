import pytest

from tests.v2_test_utils import load_fixture_document
from yaml_cli_ui.v2.context import (
    build_runtime_context,
    context_to_mapping,
    merge_with_bindings,
    resolve_selected_profile,
)
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.models import LauncherDef, ProfileDef, V2Document


def test_sequential_locals_and_imported_locals_resolution():
    doc = load_fixture_document("valid_locals.yaml")

    ctx = build_runtime_context(
        doc,
        params={"collection": "incoming"},
        selected_profile_name="home",
        run={"id": "r1"},
    )
    mapping = context_to_mapping(ctx)

    assert mapping["locals"]["run_root"] == "/work/runs/incoming"
    assert mapping["locals"]["spool_dir"] == "/work/runs/incoming/spool"
    assert mapping["locals"]["urls_file"] == "/work/runs/incoming/spool/urls.json"
    assert mapping["media"]["locals"]["scrape_script"]
    assert mapping["fs"]["locals"]["ensure_dir_script"]
    assert "from-import-" in mapping["locals"]["run_with_import"]


def test_with_values_binding_override_does_not_change_params_namespace():
    base = {
        "params": {"x": "from_params"},
        "locals": {},
        "profile": {},
        "run": {},
        "steps": {},
    }

    merged = merge_with_bindings(base, {"x": "from_binding"})

    assert merged["bindings"]["x"] == "from_binding"
    assert merged["params"]["x"] == "from_params"


def test_profile_selection_matrix():
    no_profiles = V2Document(launchers={"l": LauncherDef(title="x", use="y")})
    assert resolve_selected_profile(no_profiles) == {}

    single = V2Document(profiles={"one": ProfileDef(workdir="/one")}, launchers={"l": LauncherDef(title="x", use="y")})
    assert resolve_selected_profile(single) == {"workdir": "/one", "env": {}, "runtimes": {}}

    multiple = V2Document(
        profiles={"one": ProfileDef(workdir="/one"), "two": ProfileDef(workdir="/two")},
        launchers={"l": LauncherDef(title="x", use="y")},
    )
    with pytest.raises(V2ExecutionError, match="multiple profiles"):
        resolve_selected_profile(multiple)

    assert resolve_selected_profile(multiple, selected_profile_name="two")["workdir"] == "/two"
