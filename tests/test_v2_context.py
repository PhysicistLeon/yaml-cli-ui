# pylint: disable=import-error

from __future__ import annotations

import pytest

from yaml_cli_ui.v2.context import (
    build_runtime_context,
    evaluate_root_locals,
    merge_with_bindings,
    resolve_selected_profile,
)
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.expr import evaluate_expression
from yaml_cli_ui.v2.models import LauncherDef, ProfileDef, V2Document


def _doc(*, profiles=None, locals_map=None, imported=None) -> V2Document:
    return V2Document(
        profiles=profiles or {},
        locals=locals_map or {},
        imported_documents=imported or {},
        launchers={"main": LauncherDef(title="Main", use="commands.noop")},
    )


def test_profile_selection_rules():
    no_profiles = _doc()
    assert resolve_selected_profile(no_profiles) == {}

    one = _doc(profiles={"home": ProfileDef(workdir="/work")})
    assert resolve_selected_profile(one) == {"workdir": "/work", "env": {}, "runtimes": {}}

    multi = _doc(
        profiles={
            "home": ProfileDef(workdir="/home"),
            "srv": ProfileDef(workdir="/srv"),
        }
    )
    with pytest.raises(V2ExecutionError, match="ambiguous"):
        resolve_selected_profile(multi)

    assert resolve_selected_profile(multi, selected_profile_name="srv")["workdir"] == "/srv"
    with pytest.raises(V2ExecutionError, match="not defined"):
        resolve_selected_profile(multi, selected_profile_name="missing")


def test_root_locals_evaluated_top_to_bottom():
    doc = _doc(
        profiles={"home": ProfileDef(workdir="/work")},
        locals_map={
            "run_root": "${profile.workdir}/runs/${params.collection}",
            "spool_dir": "${locals.run_root}/spool",
            "urls_file": "${locals.spool_dir}/urls.json",
        },
    )

    locals_values = evaluate_root_locals(
        doc,
        params={"collection": "incoming"},
        selected_profile={"workdir": "/work"},
    )

    assert locals_values == {
        "run_root": "/work/runs/incoming",
        "spool_dir": "/work/runs/incoming/spool",
        "urls_file": "/work/runs/incoming/spool/urls.json",
    }


def test_forward_local_ref_fails_at_runtime():
    doc = _doc(
        locals_map={
            "later_ref": "$locals.future",
            "future": "x",
        }
    )

    with pytest.raises(V2ExecutionError, match="failed to evaluate local 'later_ref'"):
        evaluate_root_locals(doc, params={}, selected_profile={})


def test_imported_locals_available_under_alias_namespace():
    imported_media = _doc(
        locals_map={
            "script_dir": "${profile.workdir}/scripts",
            "scrape_script": "${locals.script_dir}/scrape.py",
        }
    )
    root = _doc(
        profiles={"home": ProfileDef(workdir="/work")},
        imported={"media": imported_media},
        locals_map={
            "scrape_script": "$media.locals.scrape_script",
        },
    )

    ctx = build_runtime_context(
        root,
        params={"collection": "incoming"},
        selected_profile_name="home",
    )
    mapping = ctx.as_mapping()

    assert mapping["media"]["locals"]["script_dir"] == "/work/scripts"
    assert mapping["media"]["locals"]["scrape_script"] == "/work/scripts/scrape.py"
    assert mapping["locals"]["scrape_script"] == "/work/scripts/scrape.py"


def test_with_bindings_short_name_override_and_explicit_namespaces():
    root = _doc(
        profiles={"home": ProfileDef(workdir="/work")},
        locals_map={"urls_file": "${profile.workdir}/${params.collection}.json"},
    )
    ctx = build_runtime_context(
        root,
        params={"collection": "incoming"},
        selected_profile_name="home",
        with_values={"collection": "override"},
    )

    mapping = ctx.as_mapping()
    assert evaluate_expression("collection", mapping) == "override"
    assert evaluate_expression("params.collection", mapping) == "incoming"

    merged = merge_with_bindings({"params": {"collection": "incoming"}}, {"collection": "x"})
    assert merged["collection"] == "x"
    assert merged["params"]["collection"] == "incoming"


def test_runtime_context_shape_and_no_auto_merge_imported_locals():
    imported_media = _doc(locals_map={"script": "/x.py"})
    root = _doc(
        profiles={"home": ProfileDef(workdir="/work")},
        imported={"media": imported_media},
        locals_map={"local_only": "root"},
    )

    ctx = build_runtime_context(root, params={}, selected_profile_name="home")
    mapping = ctx.as_mapping()

    for key in ("params", "locals", "profile", "run", "steps", "media"):
        assert key in mapping
    assert "script" not in mapping["locals"]
    assert mapping["media"]["locals"]["script"] == "/x.py"
