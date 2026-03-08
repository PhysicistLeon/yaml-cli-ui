from __future__ import annotations

import pytest

from yaml_cli_ui.v2.context import (
    build_runtime_context,
    merge_with_bindings,
    resolve_selected_profile,
)
from yaml_cli_ui.v2.errors import V2ExecutionError, V2ExpressionError
from yaml_cli_ui.v2.expr import evaluate_expression
from yaml_cli_ui.v2.models import ProfileDef, V2Document


def _root_doc(*, profiles: dict[str, ProfileDef] | None = None) -> V2Document:
    imported = V2Document(
        locals={
            "script_dir": "${profile.workdir}/scripts",
            "scrape_script": "${locals.script_dir}/scrape.py",
        }
    )
    return V2Document(
        profiles=profiles or {},
        locals={
            "run_root": "${profile.workdir}/runs/${params.collection}",
            "spool_dir": "${locals.run_root}/spool",
            "urls_file": "${locals.spool_dir}/urls.json",
            "scrape_script": "$media.locals.scrape_script",
        },
        imported_documents={"media": imported},
    )


def test_profile_selection_rules():
    doc_no_profiles = _root_doc(profiles={})
    assert resolve_selected_profile(doc_no_profiles) == {}

    one = _root_doc(profiles={"home": ProfileDef(workdir="/work")})
    assert resolve_selected_profile(one) == {"workdir": "/work", "env": {}, "runtimes": {}}
    assert resolve_selected_profile(one, selected_profile_name="home")["workdir"] == "/work"

    many = _root_doc(
        profiles={"a": ProfileDef(workdir="/a"), "b": ProfileDef(workdir="/b")}
    )
    with pytest.raises(V2ExecutionError, match="multiple profiles"):
        resolve_selected_profile(many)
    with pytest.raises(V2ExecutionError, match="unknown profile"):
        resolve_selected_profile(many, selected_profile_name="missing")


def test_root_locals_evaluated_top_to_bottom_and_imported_visible():
    doc = _root_doc(profiles={"home": ProfileDef(workdir="/work")})
    ctx = build_runtime_context(
        doc,
        params={"collection": "incoming"},
        selected_profile_name="home",
    )
    assert ctx.locals["run_root"] == "/work/runs/incoming"
    assert ctx.locals["spool_dir"] == "/work/runs/incoming/spool"
    assert ctx.locals["urls_file"] == "/work/runs/incoming/spool/urls.json"
    assert ctx.locals["scrape_script"] == "/work/scripts/scrape.py"


def test_forward_local_ref_fails_at_runtime():
    doc = V2Document(
        profiles={"home": ProfileDef(workdir="/work")},
        locals={
            "spool_dir": "${locals.run_root}/spool",
            "run_root": "${profile.workdir}/runs/${params.collection}",
        },
    )
    with pytest.raises(V2ExecutionError, match="failed to evaluate local 'spool_dir'"):
        build_runtime_context(doc, params={"collection": "incoming"}, selected_profile_name="home")


def test_with_bindings_short_names_and_explicit_namespaces():
    doc = _root_doc(profiles={"home": ProfileDef(workdir="/work")})
    runtime = build_runtime_context(
        doc,
        params={"collection": "incoming"},
        selected_profile_name="home",
        with_values={"collection": "override"},
    )
    ctx = runtime.as_mapping()

    assert evaluate_expression("collection", ctx) == "override"
    assert evaluate_expression("params.collection", ctx) == "incoming"


def test_context_shape_and_no_auto_merge_of_imported_locals():
    doc = _root_doc(profiles={"home": ProfileDef(workdir="/work")})
    runtime = build_runtime_context(
        doc,
        params={"collection": "incoming"},
        selected_profile_name="home",
        run={"id": "r1"},
        steps={"s": {"ok": True}},
    )
    mapping = runtime.as_mapping()

    assert set(["params", "locals", "profile", "run", "steps"]).issubset(mapping.keys())
    assert mapping["media"]["locals"]["script_dir"] == "/work/scripts"
    assert "script_dir" not in mapping["locals"]


def test_merge_with_bindings_supports_short_name_and_ambiguity():
    context = {
        "params": {"collection": "incoming"},
        "locals": {},
        "profile": {},
        "run": {},
        "steps": {},
        "loop": {},
        "error": {},
    }
    merged = merge_with_bindings(context, {"collection": "override", "source_url": "x"})
    assert evaluate_expression("collection", merged) == "override"

    ambiguous = merge_with_bindings(context, None)
    ambiguous["locals"]["collection"] = "local"
    with pytest.raises(V2ExpressionError, match="ambiguous short name"):
        evaluate_expression("collection", ambiguous)
