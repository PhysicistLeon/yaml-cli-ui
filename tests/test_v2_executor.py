# pylint: disable=import-error

from __future__ import annotations

import sys

import pytest

from yaml_cli_ui.v2.errors import V2ExecutionError
from yaml_cli_ui.v2.executor import (
    build_process_env,
    execute_command_def,
    execute_run_spec,
    resolve_program,
    resolve_workdir,
)
from yaml_cli_ui.v2.models import CommandDef, RunSpec, StepStatus


def _context(tmp_path):
    return {
        "params": {"name": "demo"},
        "locals": {},
        "profile": {
            "workdir": str(tmp_path),
            "env": {"PROFILE_VAR": "p"},
            "runtimes": {"python": sys.executable},
        },
        "run": {"id": "run_123"},
        "steps": {},
    }


def test_resolve_program_runtime_override(tmp_path):
    ctx = _context(tmp_path)
    assert resolve_program("python", ctx) == sys.executable
    assert resolve_program(sys.executable, ctx) == sys.executable


def test_resolve_workdir_priority_and_render(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(program=sys.executable, workdir="$profile.workdir/sub")
    assert resolve_workdir(run, ctx) == f"{tmp_path}/sub"

    run2 = RunSpec(program=sys.executable, workdir=None)
    assert resolve_workdir(run2, ctx) == str(tmp_path)

    ctx2 = dict(ctx)
    ctx2["profile"] = {}
    assert resolve_workdir(run2, ctx2) is None


def test_build_process_env_merge_and_render(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_ONLY", "base")
    ctx = _context(tmp_path)
    ctx["params"]["name"] = "rendered"
    run = RunSpec(
        program=sys.executable,
        env={
            "RUN_VAR": "${params.name}",
            "PROFILE_VAR": "run_override",
            "BOOL_FLAG": True,
            "NUM": 7,
        },
    )

    env = build_process_env(run, ctx)
    assert env["BASE_ONLY"] == "base"
    assert env["PROFILE_VAR"] == "run_override"
    assert env["RUN_VAR"] == "rendered"
    assert env["BOOL_FLAG"] == "True"
    assert env["NUM"] == "7"


def test_execute_success_capture_stdout(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('hello')"],
    )

    result = execute_run_spec(run, context=ctx, step_name="hello")
    assert result.status == StepStatus.SUCCESS
    assert result.exit_code == 0
    assert "hello" in (result.stdout or "")
    assert result.duration_ms is not None


def test_execute_non_zero_exit_is_failed_result(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(program=sys.executable, argv=["-c", "import sys; sys.exit(3)"])

    result = execute_run_spec(run, context=ctx, step_name="fail3")
    assert result.status == StepStatus.FAILED
    assert result.exit_code == 3


def test_execute_stderr_capture(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(program=sys.executable, argv=["-c", "import sys; print('oops', file=sys.stderr)"])

    result = execute_run_spec(run, context=ctx, step_name="stderr")
    assert result.status == StepStatus.SUCCESS
    assert "oops" in (result.stderr or "")


def test_execute_inherit_mode_returns_none_streams(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('inherit ok')"],
        stdout="inherit",
        stderr="inherit",
    )

    result = execute_run_spec(run, context=ctx, step_name="inherit")
    assert result.status == StepStatus.SUCCESS
    assert result.stdout is None
    assert result.stderr is None


def test_execute_file_mode_writes_output(tmp_path):
    ctx = _context(tmp_path)
    out_file = tmp_path / "out.txt"
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('file hello')"],
        stdout=f"file:{out_file}",
    )

    result = execute_run_spec(run, context=ctx, step_name="file")
    assert result.status == StepStatus.SUCCESS
    assert result.stdout is None
    assert out_file.read_text(encoding="utf-8").strip() == "file hello"


def test_execute_timeout_maps_to_failed_result(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "import time; time.sleep(0.2)"],
        timeout_ms=20,
    )

    result = execute_run_spec(run, context=ctx, step_name="timeout")
    assert result.status == StepStatus.FAILED
    assert result.exit_code is None
    assert result.error is not None
    assert result.error.type == "timeout"


def test_command_when_false_skips_without_subprocess(tmp_path, monkeypatch):
    ctx = _context(tmp_path)
    command = CommandDef(
        run=RunSpec(program=sys.executable, argv=["-c", "print('nope')"]),
        when=False,
    )

    called = {"value": False}

    def _fake_run(*args, **kwargs):
        called["value"] = True
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr("yaml_cli_ui.v2.executor.subprocess.run", _fake_run)
    result = execute_command_def(command, context=ctx, step_name="skip")

    assert called["value"] is False
    assert result.status == StepStatus.SKIPPED
    assert result.exit_code is None
    assert result.stdout is None
    assert result.stderr is None


def test_start_failure_raises_v2_execution_error(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(program="definitely_missing_executable_xyz_123", argv=[])

    with pytest.raises(V2ExecutionError):
        execute_run_spec(run, context=ctx, step_name="missing")


def test_invalid_stream_mode_raises(tmp_path):
    ctx = _context(tmp_path)
    run = RunSpec(program=sys.executable, argv=["-c", "print('x')"], stdout="bad")
    with pytest.raises(V2ExecutionError, match="unsupported stdout mode"):
        execute_run_spec(run, context=ctx, step_name="bad-stream")


def test_file_mode_invalid_path_raises(tmp_path):
    ctx = _context(tmp_path)
    bad_target = tmp_path / "missing" / "out.txt"
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('x')"],
        stdout=f"file:{bad_target}",
    )

    with pytest.raises(V2ExecutionError, match="failed to open stdout file"):
        execute_run_spec(run, context=ctx, step_name="bad-file")
