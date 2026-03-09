import os
from pathlib import Path

from tests.v2_test_utils import load_fixture_document, portable_python_replacements, runtime_context_mapping
from yaml_cli_ui.v2.executor import execute_command_def
from yaml_cli_ui.v2.models import CommandDef, RunSpec, StepStatus


def test_command_executor_success_nonzero_stderr_timeout_and_runtime_override(tmp_path: Path):
    doc = load_fixture_document("pipeline_success.yaml", replacements=portable_python_replacements(tmp_path))
    ctx = runtime_context_mapping(doc, profile="test")

    ok_result = execute_command_def(doc.commands["ok"], context=ctx, step_name="ok")
    assert ok_result.status == StepStatus.SUCCESS
    assert (ok_result.stdout or "").strip() == "ok"

    fail_command = CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(4)"]))
    fail_result = execute_command_def(fail_command, context=ctx, step_name="bad")
    assert fail_result.status == StepStatus.FAILED
    assert fail_result.exit_code == 4

    stderr_command = CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.stderr.write('err')"]))
    stderr_result = execute_command_def(stderr_command, context=ctx, step_name="stderr")
    assert stderr_result.status == StepStatus.SUCCESS
    assert "err" in (stderr_result.stderr or "")

    timeout_command = CommandDef(
        run=RunSpec(program="python", argv=["-c", "import time; time.sleep(0.2)"], timeout_ms=1)
    )
    timeout_result = execute_command_def(timeout_command, context=ctx, step_name="timeout")
    assert timeout_result.status == StepStatus.FAILED
    assert timeout_result.error is not None


def test_command_executor_workdir_env_and_stream_modes(tmp_path: Path):
    out_file = tmp_path / "stdout.txt"
    err_file = tmp_path / "stderr.txt"

    doc = load_fixture_document("pipeline_success.yaml", replacements=portable_python_replacements(tmp_path))
    os.environ["BASE_FROM_ENV"] = "base"
    ctx = runtime_context_mapping(doc, profile="test")
    ctx["profile"]["workdir"] = str(tmp_path)
    ctx["profile"]["env"] = {"PROFILE_ONLY": "profile", "SHARED": "profile"}

    capture_command = CommandDef(
        run=RunSpec(
            program="python",
            argv=[
                "-c",
                "import os,sys,pathlib; print(pathlib.Path.cwd().name); print(os.getenv('BASE_FROM_ENV')); print(os.getenv('PROFILE_ONLY')); print(os.getenv('RUN_ONLY')); print(os.getenv('SHARED'))",
            ],
            env={"RUN_ONLY": "run", "SHARED": "run"},
            stdout="capture",
            stderr="capture",
        )
    )
    capture_result = execute_command_def(capture_command, context=ctx, step_name="capture")
    lines = (capture_result.stdout or "").splitlines()
    assert capture_result.status == StepStatus.SUCCESS
    assert lines[0] == tmp_path.name
    assert lines[1] == "base"
    assert lines[2] == "profile"
    assert lines[3] == "run"
    assert lines[4] == "run"

    inherit_command = CommandDef(
        run=RunSpec(
            program="python",
            argv=["-c", "print('x'); import sys; sys.stderr.write('y')"],
            stdout="inherit",
            stderr="inherit",
        )
    )
    inherit_result = execute_command_def(inherit_command, context=ctx, step_name="inherit")
    assert inherit_result.status == StepStatus.SUCCESS
    assert inherit_result.stdout is None
    assert inherit_result.stderr is None

    file_command = CommandDef(
        run=RunSpec(
            program="python",
            argv=["-c", "import sys; print('out'); sys.stderr.write('err')"],
            stdout=f"file:{out_file}",
            stderr=f"file:{err_file}",
        )
    )
    file_result = execute_command_def(file_command, context=ctx, step_name="file")
    assert file_result.status == StepStatus.SUCCESS
    assert out_file.read_text(encoding="utf-8").strip() == "out"
    assert err_file.read_text(encoding="utf-8").strip() == "err"
