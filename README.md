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
