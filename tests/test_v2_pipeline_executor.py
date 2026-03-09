from __future__ import annotations

import sys

import pytest

from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.executor import (
    execute_command_def,
    execute_pipeline_def,
    execute_step,
    resolve_callable,
)
from yaml_cli_ui.v2.models import (
    CommandDef,
    ForeachSpec,
    OnErrorSpec,
    PipelineDef,
    RunSpec,
    StepSpec,
    StepStatus,
    V2Document,
)


def _base_context(params: dict | None = None) -> dict:
    return {
        "params": params or {},
        "locals": {},
        "profile": {"runtimes": {"python": sys.executable}},
        "run": {},
        "steps": {},
        "bindings": {},
    }


def _py_ok(msg: str = "ok") -> CommandDef:
    return CommandDef(run=RunSpec(program="python", argv=["-c", f"print('{msg}')"]))


def _py_fail(code: int = 3) -> CommandDef:
    return CommandDef(run=RunSpec(program="python", argv=["-c", f"import sys; sys.exit({code})"]))


def test_simple_pipeline_success():
    doc = V2Document(commands={"first": _py_ok("1"), "second": _py_ok("2")})
    pipeline = PipelineDef(steps=["first", "second"])

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert result.status == StepStatus.SUCCESS
    assert list(result.children.keys()) == ["first", "second"]


def test_nested_pipeline_children_preserved():
    doc = V2Document(
        commands={"inner_cmd": _py_ok()},
        pipelines={"inner": PipelineDef(steps=["inner_cmd"]), "outer": PipelineDef(steps=["inner"])},
    )

    result = execute_pipeline_def(doc.pipelines["outer"], doc=doc, context=_base_context())

    assert result.status == StepStatus.SUCCESS
    assert result.children["inner"].children["inner_cmd"].status == StepStatus.SUCCESS


def test_short_step_syntax_and_unique_name_generation():
    doc = V2Document(commands={"hello": _py_ok("hello")})
    pipeline = PipelineDef(steps=["hello", "hello"])

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert list(result.children.keys()) == ["hello", "hello_2"]


def test_namespaced_short_step_uses_basename_and_dedupes():
    imported = V2Document(commands={"fetch": _py_ok("ok")})
    root = V2Document(imported_documents={"media": imported})
    pipeline = PipelineDef(steps=["media.fetch", "media.fetch"])

    result = execute_pipeline_def(pipeline, doc=root, context=_base_context())

    assert list(result.children.keys()) == ["fetch", "fetch_2"]


def test_expanded_step_with_bindings_overrides_short_name_resolution():
    doc = V2Document(
        commands={
            "print_collection": CommandDef(
                run=RunSpec(program="python", argv=["-c", "import sys; print(sys.argv[1], sys.argv[2])", "$collection", "$params.collection"])
            )
        }
    )
    pipeline = PipelineDef(
        steps=[StepSpec(use="print_collection", with_values={"collection": "binding_collection"})]
    )

    result = execute_pipeline_def(
        pipeline,
        doc=doc,
        context=_base_context(params={"collection": "root_collection"}),
    )

    assert result.children["print_collection"].status == StepStatus.SUCCESS
    assert "binding_collection root_collection" in (result.children["print_collection"].stdout or "")


def test_step_when_false_skips_and_pipeline_continues():
    doc = V2Document(commands={"ok": _py_ok()})
    pipeline = PipelineDef(steps=[StepSpec(step="s1", use="ok", when="${false}"), "ok"])

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert result.children["s1"].status == StepStatus.SKIPPED
    assert result.children["ok"].status == StepStatus.SUCCESS


def test_step_when_evaluates_after_with_bindings():
    doc = V2Document(commands={"ok": _py_ok()})
    pipeline = PipelineDef(
        steps=[
            StepSpec(
                step="bound_step",
                use="ok",
                with_values={"mode": "video"},
                when="${mode == 'video'}",
            )
        ]
    )

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert result.children["bound_step"].status == StepStatus.SUCCESS


def test_command_failure_stops_pipeline():
    doc = V2Document(commands={"bad": _py_fail(), "ok": _py_ok()})

    result = execute_pipeline_def(PipelineDef(steps=["bad", "ok"]), doc=doc, context=_base_context())

    assert result.status == StepStatus.FAILED
    assert list(result.children.keys()) == ["bad"]


def test_step_continue_on_error_keeps_going_but_pipeline_failed():
    doc = V2Document(commands={"bad": _py_fail(), "ok": _py_ok()})
    pipeline = PipelineDef(steps=[StepSpec(use="bad", continue_on_error=True), "ok"])

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert result.children["bad"].status == StepStatus.FAILED
    assert result.children["ok"].status == StepStatus.SUCCESS
    assert result.status == StepStatus.FAILED


def test_foreach_success_meta_and_children():
    doc = V2Document(commands={"echo": _py_ok()})
    pipeline = PipelineDef(
        steps=[
            StepSpec(
                step="per_job",
                foreach=ForeachSpec(
                    in_expr="$params.jobs",
                    as_name="job",
                    steps=["echo"],
                ),
            )
        ]
    )

    result = execute_pipeline_def(
        pipeline,
        doc=doc,
        context=_base_context(params={"jobs": [{"name": "a"}, {"name": "b"}]}),
    )

    foreach_result = result.children["per_job"]
    assert foreach_result.meta["iteration_count"] == 2
    assert list(foreach_result.children.keys()) == ["iter_0", "iter_1"]


def test_foreach_loop_vars_available():
    doc = V2Document(
        commands={
            "loop_echo": CommandDef(
                run=RunSpec(
                    program="python",
                    argv=[
                        "-c",
                        "import sys; print(sys.argv[1], sys.argv[2], sys.argv[3])",
                        "$loop.index",
                        "$loop.first",
                        "$loop.last",
                    ],
                )
            )
        }
    )
    pipeline = PipelineDef(
        steps=[
            StepSpec(
                step="per",
                foreach=ForeachSpec(in_expr="$params.jobs", as_name="job", steps=["loop_echo"]),
            )
        ]
    )

    result = execute_pipeline_def(
        pipeline,
        doc=doc,
        context=_base_context(params={"jobs": [{"x": 1}, {"x": 2}]}),
    )

    assert "0 True False" in (result.children["per"].children["iter_0"].children["loop_echo"].stdout or "")
    assert "1 False True" in (result.children["per"].children["iter_1"].children["loop_echo"].stdout or "")


def test_foreach_invalid_input_raises():
    doc = V2Document(commands={"ok": _py_ok()})
    pipeline = PipelineDef(
        steps=[StepSpec(step="bad_foreach", foreach=ForeachSpec(in_expr="$params.jobs", as_name="job", steps=["ok"]))]
    )

    with pytest.raises(V2ExecutionError, match="foreach.in must evaluate to a list"):
        execute_pipeline_def(pipeline, doc=doc, context=_base_context(params={"jobs": "oops"}))


def test_command_on_error_recovered():
    doc = V2Document(
        commands={
            "bad": CommandDef(
                run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(5)"]),
                on_error=OnErrorSpec(steps=["recover"]),
            ),
            "recover": _py_ok("recovered"),
        }
    )

    result = execute_pipeline_def(PipelineDef(steps=["bad"]), doc=doc, context=_base_context())

    assert result.status == StepStatus.SUCCESS
    assert result.children["bad"].status == StepStatus.RECOVERED


def test_direct_execute_command_def_on_error_recovered():
    doc = V2Document(commands={"recover": _py_ok("r")})
    command = CommandDef(
        run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(9)"]),
        on_error=OnErrorSpec(steps=["recover"]),
    )

    result = execute_command_def(command, context=_base_context(), step_name="bad", doc=doc)

    assert result.status == StepStatus.RECOVERED
    assert result.meta["on_error"].status == StepStatus.SUCCESS


def test_direct_execute_command_def_on_error_requires_doc():
    command = CommandDef(
        run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(9)"]),
        on_error=OnErrorSpec(steps=["recover"]),
    )

    with pytest.raises(V2ExecutionError, match="doc is required"):
        execute_command_def(command, context=_base_context(), step_name="bad")


def test_pipeline_on_error_recovered_and_failed_recovery():
    recover_doc = V2Document(
        commands={"bad": _py_fail(), "recover": _py_ok()},
    )
    recovered = execute_pipeline_def(
        PipelineDef(steps=["bad"], on_error=OnErrorSpec(steps=["recover"])),
        doc=recover_doc,
        context=_base_context(),
    )
    assert recovered.status == StepStatus.RECOVERED

    fail_doc = V2Document(commands={"bad": _py_fail(), "recover_bad": _py_fail(7)})
    failed = execute_pipeline_def(
        PipelineDef(steps=["bad"], on_error=OnErrorSpec(steps=["recover_bad"])),
        doc=fail_doc,
        context=_base_context(),
    )
    assert failed.status == StepStatus.FAILED
    assert failed.error is not None
    assert failed.error.step == "bad"
    assert failed.meta.get("recovery_error") is not None


def test_steps_updated_incrementally_for_next_steps():
    doc = V2Document(
        commands={
            "emit": CommandDef(run=RunSpec(program="python", argv=["-c", "print('alpha')"])),
            "consume": CommandDef(
                run=RunSpec(
                    program="python",
                    argv=["-c", "import sys; print(sys.argv[1].strip())", "$steps.first.stdout"],
                )
            ),
        }
    )
    pipeline = PipelineDef(
        steps=[
            StepSpec(step="first", use="emit"),
            StepSpec(step="second", use="consume"),
        ]
    )

    result = execute_pipeline_def(pipeline, doc=doc, context=_base_context())

    assert result.children["second"].status == StepStatus.SUCCESS
    assert "alpha" in (result.children["second"].stdout or "")


def test_resolve_callable_supports_import_namespace():
    imported = V2Document(commands={"ping": _py_ok()})
    root = V2Document(imported_documents={"media": imported})

    resolved = resolve_callable(root, "media.ping")

    assert isinstance(resolved, CommandDef)


def test_execute_step_rejects_invalid_use_name():
    doc = V2Document(commands={"ok": _py_ok()})

    with pytest.raises(V2ExecutionError, match="callable 'missing' not found"):
        execute_step(StepSpec(use="missing"), doc=doc, context=_base_context())
