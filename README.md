# YAML CLI UI

[![Pylint](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/pylint.yml?branch=main&label=pylint)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/pylint.yml)
[![Ruff](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/lint.yml?branch=main&label=ruff)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/lint.yml)
[![Coverage](https://img.shields.io/codecov/c/github/PhysicistLeon/yaml-cli-ui?label=coverage)](https://app.codecov.io/gh/PhysicistLeon/yaml-cli-ui)

Python app that loads workflow YAML, renders top-level actions as launch buttons, opens per-action parameter dialogs, serializes argv deterministically, and executes CLI pipelines with safe `subprocess.run(..., shell=False)` defaults.

## Run

```bash
python main.py examples/yt_audio.yaml
# or with startup settings from ini
python main.py --settings app.ini
```

## Features

- Top-level actions rendered as quick-launch buttons (no action dropdown).
- Action parameters are entered in a modal dialog per run.
- Last entered action parameters are remembered between app restarts (per YAML config and action, excluding `secret` fields) and prefilled on next run.
- Parallel action runs with status colors: idle=neutral, running=yellow, success=green, failed=red.
- Output notebook with aggregate `All runs` stream plus per-action tabs.
- Per-action run history selector to inspect past outputs.
- Supported steps: `run`, nested `pipeline`, `foreach`.
- Safe expression evaluator for `${...}` templates.
- Deterministic argv serialization (string/short-map/extended-option forms).
- Step result storage (`exit_code/stdout/stderr/duration_ms`).
- YAML reload button in UI.


## Runtime aliases

You can define runtime-level executable overrides, for example for Python:

```yaml
runtime:
  python:
    executable: "C:\\code\\Python\\.venvs\\stable3_12_4\\Scripts\\python.exe"

actions:
  run_script:
    title: "Run Python script"
    pipeline:
      - id: run
        run:
          program: python
          argv:
            - "scripts\\process.py"
```

When `program: python` is used in a step, the configured `runtime.python.executable` is used instead.


## UI flow

1. Click any action button on the main screen.
2. If the action has editable parameters, fill them in the modal dialog and press **Run**.
3. If the action has no editable parameters, it starts immediately without opening a dialog.
4. If validation fails, run does not start and button status color is unchanged.
5. While action is running, its button is yellow.
6. After completion, button turns green on success or red on failure.
7. Inspect logs in `All runs` (aggregate) or the action-specific tab/history.


## INI startup settings

You can provide a `--settings` ini file to define:

- which YAML should be loaded by default on startup;
- which folder should open first when pressing **Browse**.

Example `app.ini`:

```ini
[ui]
default_yaml = examples/yt_audio.yaml
browse_dir = examples
```

A ready-to-use example is included in the repo: `examples/app.ini`.

Relative paths in ini are resolved relative to the ini file location.
