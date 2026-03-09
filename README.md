# YAML CLI UI

[![Pylint](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/pylint.yml?branch=main&label=pylint)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/pylint.yml)
[![Ruff](https://img.shields.io/github/actions/workflow/status/PhysicistLeon/yaml-cli-ui/lint.yml?branch=main&label=ruff)](https://github.com/PhysicistLeon/yaml-cli-ui/actions/workflows/lint.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/PhysicistLeon/yaml-cli-ui/main/coverage-badge.json)](./coverage-badge.json)

YAML CLI UI now supports **two config generations side-by-side**:

- **v1 legacy** (`version: 1`) — action-centric model (`actions`, legacy engine/UI/storage).
- **v2-lite current** (`version: 2`) — launcher-centric model (`launchers`, `commands`, `pipelines`, `params`, `locals`, `imports`, `profiles`) with dedicated v2 persistence.

## Quick start

```bash
python main.py examples/yt_audio.yaml         # v1 legacy example
python main.py examples/v2_minimal.yaml       # v2-lite example
python main.py examples/v2_ingest_demo.yaml   # fuller v2-lite example
```

Routing is automatic and explicit by top-level `version`:

- `version: 1` -> `yaml_cli_ui.app.App` (legacy v1)
- `version: 2` -> `yaml_cli_ui.app_v2.AppV2` (v2 stack)

## What is legacy v1

Legacy v1 keeps the original contract and behavior:

- action-centric YAML (`actions`, `vars`, legacy args DSL);
- legacy engine/app modules (`yaml_cli_ui/app.py`, `yaml_cli_ui/engine.py`, `yaml_cli_ui/presets.py`);
- legacy presets/state shape (`<yaml>.presets.json`).

No auto-rewrite or semantics rewrite is performed in this migration step.

## What is current v2-lite

v2-lite is the current migration target:

- `launchers` as UI entry points;
- reusable callable graph: `commands` + `pipelines` (+ `imports`);
- root-level `params`, ordered `locals`, and optional `profiles`;
- explicit context namespaces (`$params`, `$locals`, `$profile`, `$steps`, `$run`, `$loop`, `$error`);
- dedicated v2 persistence files for launcher presets and last values.

## Running with startup settings

```bash
python main.py --settings app.ini
```

`app.ini` may define default YAML and browse directory:

```ini
[ui]
default_yaml = examples/v2_minimal.yaml
browse_dir = examples
```

## Migration docs

- v2-lite reference spec: `docs/v2_spec.md`
- v1 -> v2 manual migration guide: `docs/v1_to_v2_migration.md`
- examples guide: `docs/v2_examples.md`
- routing details: `docs/v1_v2_routing.md`
- v2 persistence details: `docs/v2_persistence.md`

## Intentionally deferred / not implemented

These are deliberately out of scope right now:

- `parallel` execution;
- `param_imports` model;
- auto-migration converter (config or storage) from v1 to v2;
- richer public foreach result addressing beyond current runtime model;
- importing `launchers`, `profiles`, or `params` as library sections.
