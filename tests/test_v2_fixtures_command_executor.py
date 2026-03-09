from tests.v2_test_utils import load_fixture_document
from yaml_cli_ui.v2.executor import execute_command_def
from yaml_cli_ui.v2.models import CommandDef, RunSpec, StepStatus


def _ctx(**kwargs):
    ctx = {"params": {}, "locals": {}, "profile": {}, "run": {}, "steps": {}, "bindings": {}}
    ctx.update(kwargs)
    return ctx


def test_command_success_nonzero_stderr_and_timeout():
    ok = execute_command_def(CommandDef(run=RunSpec(program="python", argv=["-c", "print('ok')"])), context=_ctx())
    assert ok.status == StepStatus.SUCCESS
    assert (ok.stdout or "").strip() == "ok"

    bad = execute_command_def(CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.exit(3)"])), context=_ctx())
    assert bad.status == StepStatus.FAILED
    assert bad.exit_code == 3

    err = execute_command_def(CommandDef(run=RunSpec(program="python", argv=["-c", "import sys; sys.stderr.write('e')"])), context=_ctx())
    assert err.status == StepStatus.SUCCESS
    assert err.stderr == "e"

    timeout = execute_command_def(CommandDef(run=RunSpec(program="python", argv=["-c", "import time; time.sleep(0.2)"], timeout_ms=50)), context=_ctx())
    assert timeout.status == StepStatus.FAILED
    assert timeout.error and timeout.error.type == "timeout"


def test_runtime_override_workdir_env_and_stream_modes(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_FROM_ENV", "base")

    stdout_file = tmp_path / "out.txt"
    stderr_file = tmp_path / "err.txt"
    cwd_probe = tmp_path / "cwd.txt"
    command = CommandDef(
        run=RunSpec(
            program="python",
            argv=["-c", "import os,pathlib,sys; pathlib.Path('cwd.txt').write_text(os.getcwd()); print(os.getenv('A')); print(os.getenv('BASE_FROM_ENV')); sys.stderr.write('se')"],
            stdout=f"file:{stdout_file}",
            stderr=f"file:{stderr_file}",
            env={"A": "run"},
        )
    )
    result = execute_command_def(
        command,
        context=_ctx(profile={"workdir": str(tmp_path), "env": {"A": "profile"}, "runtimes": {"python": "python"}}),
    )

    assert result.status == StepStatus.SUCCESS
    assert result.stdout is None and result.stderr is None
    assert stdout_file.read_text().strip().splitlines() == ["run", "base"]
    assert stderr_file.read_text() == "se"
    assert cwd_probe.exists()

    inherit = execute_command_def(
        CommandDef(run=RunSpec(program="python", argv=["-c", "print('x')"], stdout="inherit", stderr="inherit")),
        context=_ctx(),
    )
    assert inherit.status == StepStatus.SUCCESS


def test_fixture_replacements_cover_import_subtree():
    doc = load_fixture_document(
        "with_imports_root.yaml",
        replacements={"python": "__PYTHON__", "scripts/ensure_dir.py": "__TMPDIR__/ensure.py"},
    )

    assert "media" in doc.imported_documents
    assert doc.imported_documents["fs"].locals["ensure_dir_script"].startswith("__TMPDIR__")
