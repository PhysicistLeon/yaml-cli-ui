# pylint: disable=import-error

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from yaml_cli_ui.v2.executor import (
    build_process_env,
    execute_command_def,
    execute_run_spec,
    resolve_program,
    resolve_workdir,
)
from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.models import CommandDef, RunSpec, StepStatus


def _ctx(tmp_path: Path | None = None) -> dict:
    profile_workdir = str(tmp_path) if tmp_path is not None else None
    return {
        "params": {"name": "demo"},
        "locals": {},
        "profile": {
            "workdir": profile_workdir,
            "env": {"PROFILE_VAR": "p", "SHARED": "profile"},
            "runtimes": {"python": sys.executable},
        },
        "run": {"id": "run_123"},
        "steps": {},
    }


def test_resolve_program_uses_runtime_override():
    assert resolve_program("python", _ctx()) == sys.executable


def test_resolve_program_falls_back_to_literal_when_override_missing():
    assert resolve_program("/bin/custom", _ctx()) == "/bin/custom"


def test_resolve_workdir_priority_and_default(tmp_path: Path):
    ctx = _ctx(tmp_path)
    run = RunSpec(program=sys.executable, workdir="$params.name")
    assert resolve_workdir(run, ctx) == "demo"

    run_profile = RunSpec(program=sys.executable)
    assert resolve_workdir(run_profile, ctx) == str(tmp_path)

    no_profile_ctx = _ctx()
    no_profile_ctx["profile"] = {}
    assert resolve_workdir(run_profile, no_profile_ctx) is None


def test_build_process_env_merge_and_rendering(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EXEC_BASE", "base")
    run = RunSpec(
        program=sys.executable,
        env={"RUN_NAME": "$params.name", "RUN_BOOL": True, "SHARED": "run"},
    )

    env = build_process_env(run, _ctx())

    assert env["EXEC_BASE"] == "base"
    assert env["PROFILE_VAR"] == "p"
    assert env["RUN_NAME"] == "demo"
    assert env["RUN_BOOL"] == "True"
    assert env["SHARED"] == "run"


def test_simple_success_execution():
    run = RunSpec(program=sys.executable, argv=["-c", "print('hello')"])

    result = execute_run_spec(run, context=_ctx(), step_name="hello")

    assert result.status == StepStatus.SUCCESS
    assert result.exit_code == 0
    assert "hello" in (result.stdout or "")
    assert result.duration_ms is not None
    assert result.started_at is not None
    assert result.finished_at is not None


def test_non_zero_exit_is_failed_result_not_exception():
    run = RunSpec(program=sys.executable, argv=["-c", "import sys; sys.exit(3)"])

    result = execute_run_spec(run, context=_ctx(), step_name="bad")

    assert result.status == StepStatus.FAILED
    assert result.exit_code == 3


def test_stderr_capture():
    run = RunSpec(program=sys.executable, argv=["-c", "import sys; sys.stderr.write('err!')"])

    result = execute_run_spec(run, context=_ctx(), step_name="stderr")

    assert result.status == StepStatus.SUCCESS
    assert "err!" in (result.stderr or "")


def test_inherit_mode_has_none_stream_fields():
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('x'); import sys; sys.stderr.write('y')"],
        stdout="inherit",
        stderr="inherit",
    )

    result = execute_run_spec(run, context=_ctx(), step_name="inherit")

    assert result.status == StepStatus.SUCCESS
    assert result.stdout is None
    assert result.stderr is None


def test_file_mode_writes_output(tmp_path: Path):
    output_path = tmp_path / "out.txt"
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('file-out')"],
        stdout=f"file:{output_path}",
    )

    result = execute_run_spec(run, context=_ctx(), step_name="file")

    assert result.status == StepStatus.SUCCESS
    assert result.stdout is None
    assert output_path.read_text(encoding="utf-8").strip() == "file-out"


def test_timeout_maps_to_failed_result():
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "import time; time.sleep(0.2)"],
        timeout_ms=10,
    )

    result = execute_run_spec(run, context=_ctx(), step_name="timeout")

    assert result.status == StepStatus.FAILED
    assert result.exit_code is None
    assert result.error is not None
    assert result.error.type == "timeout"


def test_when_false_skips_command():
    command = CommandDef(
        when="${false}",
        run=RunSpec(program=sys.executable, argv=["-c", "print('should not run')"]),
    )

    result = execute_command_def(command, context=_ctx(), step_name="conditional")

    assert result.status == StepStatus.SKIPPED
    assert result.exit_code is None
    assert result.stdout is None
    assert result.stderr is None


def test_start_failure_raises_v2_execution_error():
    run = RunSpec(program="definitely-not-existing-program-xyz")

    with pytest.raises(V2ExecutionError, match="failed to start program"):
        execute_run_spec(run, context=_ctx(), step_name="missing")


def test_invalid_env_value_raises_execution_error():
    run = RunSpec(program=sys.executable, env={"BAD": {"nested": "x"}})

    with pytest.raises(V2ExecutionError, match="must render to scalar"):
        build_process_env(run, _ctx())


def test_invalid_file_mode_target_raises_execution_error(tmp_path: Path):
    invalid_path = tmp_path / "missing-parent" / "out.txt"
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('x')"],
        stdout=f"file:{invalid_path}",
    )

    with pytest.raises(V2ExecutionError, match="failed to open stdout file"):
        execute_run_spec(run, context=_ctx(), step_name="badfile")
