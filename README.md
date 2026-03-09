# YAML CLI UI

[![Pylint](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/pylint.yml?branch=main&label=pylint)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/pylint.yml)
[![Ruff](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/lint.yml?branch=main&label=ruff)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/lint.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/PhysicistLeon/yaml-cli-ui/main/coverage-badge.json)](./coverage-badge.json)

YAML CLI UI now supports **side-by-side config versions**:

- **v1 (legacy)**: action-centric flow (`actions`, legacy engine/UI/storage contract).
- **v2-lite (current)**: launcher/callable flow (`launchers`, `commands`, `pipelines`, `imports`, `profiles`, `params`, `locals`) with dedicated v2 persistence.

## Quick start

```bash
# open explicit config
python main.py examples/yt_audio.yaml
python main.py examples/v2_minimal.yaml

# or resolve startup config from ini ([ui] default_yaml + browse_dir)
python main.py --settings app.ini
```

Routing is explicit by root `version` field:

- `version: 1` -> legacy `App` stack (`yaml_cli_ui/app.py`, `engine.py`, `presets.py`)
- `version: 2` -> `AppV2` + `yaml_cli_ui/v2/*`

## Features

- Top-level actions rendered as quick-launch buttons (no action dropdown).
- Optional `actions.<id>.info` tooltip on action buttons (shown on hover with delay).
- Action parameters are entered in a modal dialog per run.
- Last entered action parameters are remembered between app restarts (per YAML config and action, excluding `secret` fields) and prefilled on next run.
- Named presets per action (create/overwrite/rename/delete) stored next to YAML in `<yaml>.presets.json`.
- Last run behavior supports snapshot or reference to the last launched named preset.
- Preset compatibility warnings show unused parameters when YAML form fields changed.
- Parallel action runs with status colors: idle=neutral, running=yellow, success=green, failed=red.
- Output notebook with aggregate `All runs` stream plus per-action tabs.
- Per-action run history selector to inspect past outputs.
- Supported steps: `run`, nested `pipeline`, `foreach`.
- Safe expression evaluator for `${...}` templates.
- Deterministic argv serialization (string/short-map/extended-option forms).
- Step result storage (`exit_code/stdout/stderr/duration_ms`) with recovery namespace keys (`_recovery.<step_id>`).
- Optional `on_error` action block with `${error.*}` context (`step_id`, `exit_code`, `message`, `type`).
- Recovered action status is shown in orange (`recovered`).

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

## Presets JSON (`<yaml>.presets.json`)

Action argument values can be stored and reused via a JSON file placed next to the selected YAML config.

Path rule:

- If config is `workflow.yaml`, presets file is `workflow.yaml.presets.json`.

Behavior:

- Stores named presets per action.
- Stores last-run state as snapshot or reference to a named preset.
- Ignores removed/unknown form fields when applying old presets and shows a compatibility warning.
- Excludes fields with `type: secret` from persisted values.

Minimal file example:

```json
{
  "version": 1,
  "actions": {
    "build": {
      "presets": {
        "smoke": {
          "values": {
            "target": "tests",
            "verbose": true
          }
        }
      },
      "last_run": {
        "mode": "preset_ref",
        "preset_name": "smoke"
      }
    }
  }
}
```



## on_error demo

A minimal runnable demo for the new recovery behavior is included:

```bash
python main.py examples/on_error_demo.yaml
```

This action intentionally fails, then runs `on_error` cleanup and passes `${error.*}` context to cleanup script.



## What is legacy v1

v1 remains supported and intentionally untouched for backward compatibility:

- action-centric schema (`actions`, legacy `vars` semantics, v1 argv DSL forms)
- legacy runtime path in `yaml_cli_ui/app.py` + `yaml_cli_ui/engine.py`
- legacy persistence shape in `<config>.presets.json`

## What is current v2-lite

v2-lite provides:

- `launchers` as UI entrypoints
- callable namespace with `commands` and `pipelines`
- ordered root `locals`
- root `params` and optional `profiles`
- `imports` for reusable command/pipeline/local packs
- step-level `foreach` and `on_error`
- explicit runtime namespaces (`$params`, `$locals`, `$profile`, `$steps`, `$run`, `$loop`, `$error`)
- v2 persistence split:
  - `<config>.launchers.presets.json`
  - `<config>.state.json`

## Examples

- Legacy v1: `examples/yt_audio.yaml`
- Minimal v2: `examples/v2_minimal.yaml`
- Fuller v2 demo: `examples/v2_ingest_demo.yaml`


## Legacy bridge (for existing v1 users)

- Existing `version: 1` configs remain supported; no immediate rewrite is required.
- Keep using legacy reference docs for v1 syntax/behavior: `docs/yaml_pipeline_reference.md`.
- Migrate only when needed, using `docs/v1_to_v2_migration.md` as a manual checklist.

## Migration docs

- v2-lite reference spec: `docs/v2_spec.md`
- v1 -> v2 migration guide: `docs/v1_to_v2_migration.md`
- v2 examples guide: `docs/v2_examples.md`
- side-by-side routing notes: `docs/v1_v2_routing.md`
- v2 persistence details: `docs/v2_persistence.md`

## Intentionally not implemented / deferred

The following are intentionally out of scope right now:

- `parallel` execution semantics
- `param_imports` merge model
- auto-migration of v1 config or storage to v2
- richer public foreach result addressing model beyond current runtime context
- importing `launchers` / `profiles` as library sections

## Notes

- No auto-converter is provided; migration is manual.
- Legacy v1 behavior is preserved.
- Process execution keeps safe defaults (`subprocess.run(..., shell=False)`).
