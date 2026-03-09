# pylint: disable=import-error,duplicate-code

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import pytest

from yaml_cli_ui.v2.executor import (
    _looks_like_python_program,
    _sanitize_child_env_for_embedded_tk,
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
    run = RunSpec(program=sys.executable, workdir="${profile.workdir}/sub")
    assert resolve_workdir(run, ctx) == f"{tmp_path}/sub"

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


def test_looks_like_python_program_detection():
    assert _looks_like_python_program("python")
    assert _looks_like_python_program("python.exe")
    assert _looks_like_python_program(r"C:/venv/Scripts/python.exe")
    assert _looks_like_python_program(r"C:\venv\Scripts\python.exe")
    assert _looks_like_python_program("python3")
    assert not _looks_like_python_program("py")
    assert not _looks_like_python_program("node")


def test_sanitize_child_env_for_embedded_tk():
    env = {
        "PATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345;C:\Windows\System32",
        "TCL_LIBRARY": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tcl_data",
        "TK_LIBRARY": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tk_data",
        "PYTHONHOME": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345",
        "PYTHONPATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345",
        "TCLLIBPATH": r"C:\Users\Astra\AppData\Local\Temp\_MEI12345\_tcl_data",
        "SYSTEMROOT": r"C:\Windows",
    }

    sanitized = _sanitize_child_env_for_embedded_tk(env)

    assert "PATH" not in sanitized
    assert "TCL_LIBRARY" not in sanitized
    assert "TK_LIBRARY" not in sanitized
    assert "PYTHONHOME" not in sanitized
    assert "PYTHONPATH" not in sanitized
    assert "TCLLIBPATH" not in sanitized
    assert sanitized["SYSTEMROOT"] == r"C:\Windows"


def test_execute_run_spec_sanitizes_env_for_frozen_python_child_with_runtime_alias(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_env: dict[str, str] = {}

    def _fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("yaml_cli_ui.v2.executor.subprocess.run", _fake_run)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    context = _ctx()
    context["profile"]["runtimes"]["py312"] = r"C:\Python312\python.exe"

    run = RunSpec(
        program="py312",
        argv=["-c", "print('ok')"],
        env={
            "PATH": r"C:\Temp\_MEI12345;C:\Windows\System32",
            "TCL_LIBRARY": r"C:\Temp\_MEI12345\_tcl_data",
            "SYSTEMROOT": r"C:\Windows",
        },
    )

    result = execute_run_spec(run, context=context, step_name="python")

    assert result.status == StepStatus.SUCCESS
    assert "PATH" not in captured_env
    assert "TCL_LIBRARY" not in captured_env
    assert captured_env["SYSTEMROOT"] == r"C:\Windows"


def test_execute_run_spec_does_not_sanitize_for_frozen_non_python_child(monkeypatch: pytest.MonkeyPatch):
    captured_env: dict[str, str] = {}

    def _fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("yaml_cli_ui.v2.executor.subprocess.run", _fake_run)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    run = RunSpec(
        program="node",
        argv=["-e", "console.log('ok')"],
        env={"PATH": r"C:\Temp\_MEI12345;C:\Windows\System32"},
    )

    execute_run_spec(run, context=_ctx(), step_name="node")

    assert captured_env["PATH"] == r"C:\Temp\_MEI12345;C:\Windows\System32"


def test_execute_run_spec_does_not_sanitize_when_not_frozen(monkeypatch: pytest.MonkeyPatch):
    captured_env: dict[str, str] = {}

    def _fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("yaml_cli_ui.v2.executor.subprocess.run", _fake_run)
    monkeypatch.delattr(sys, "frozen", raising=False)

    run = RunSpec(
        program="python",
        argv=["-c", "print('ok')"],
        env={"PATH": r"C:\Temp\_MEI12345;C:\Windows\System32"},
    )

    execute_run_spec(run, context=_ctx(), step_name="python")

    assert captured_env["PATH"] == r"C:\Temp\_MEI12345;C:\Windows\System32"


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


def test_when_false_does_not_invoke_subprocess(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("subprocess.run must not be called when command is skipped")

    monkeypatch.setattr("yaml_cli_ui.v2.executor.subprocess.run", _fake_run)

    command = CommandDef(
        when="${false}",
        run=RunSpec(program=sys.executable, argv=["-c", "print('should not run')"]),
    )

    result = execute_command_def(command, context=_ctx(), step_name="conditional")

    assert result.status == StepStatus.SKIPPED
    assert not calls


def test_start_failure_raises_v2_execution_error():
    run = RunSpec(program="definitely-not-existing-program-xyz")

    with pytest.raises(V2ExecutionError, match="failed to start program"):
        execute_run_spec(run, context=_ctx(), step_name="missing")


def test_invalid_env_value_raises_execution_error():
    run = RunSpec(program=sys.executable, env={"BAD": {"nested": "x"}})

    with pytest.raises(V2ExecutionError, match="must render to scalar"):
        build_process_env(run, _ctx())


def test_invalid_stream_mode_raises_execution_error():
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('x')"],
        stdout="bad",
    )

    with pytest.raises(V2ExecutionError, match="unsupported stdout mode"):
        execute_run_spec(run, context=_ctx(), step_name="badstream")


def test_invalid_file_mode_target_raises_execution_error(tmp_path: Path):
    invalid_path = tmp_path / "missing-parent" / "out.txt"
    run = RunSpec(
        program=sys.executable,
        argv=["-c", "print('x')"],
        stdout=f"file:{invalid_path}",
    )

    with pytest.raises(V2ExecutionError, match="failed to open stdout file"):
        execute_run_spec(run, context=_ctx(), step_name="badfile")
