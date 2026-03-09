# v2 golden fixtures and regression tests

This document captures the step-10 golden test suite for `yaml_cli_ui.v2`.

## Fixture suite (tests/fixtures/v2)

- Loader/import basics: `minimal_root.yaml`, `with_imports_root.yaml`, `packs/media.yaml`, `packs/fs.yaml`
- Locals/context: `valid_locals.yaml`, `invalid_future_local.yaml`
- Argv DSL: `argv_mixed.yaml`
- Pipeline/executor flows: `pipeline_success.yaml`, `pipeline_continue_on_error.yaml`, `pipeline_on_error_recovered.yaml`, `foreach_success.yaml`, `foreach_invalid_input.yaml`
- Validator negatives: `conflict_callable_names.yaml`, `invalid_imported_with_launchers_root.yaml`, `packs/invalid_with_launchers.yaml`
- Integration-like smoke case: `full_ingest_like.yaml`

## Golden test layers

- `tests/test_v2_fixtures_loader.py`
- `tests/test_v2_fixtures_validator.py`
- `tests/test_v2_fixtures_expr_renderer.py`
- `tests/test_v2_fixtures_context.py`
- `tests/test_v2_fixtures_argv.py`
- `tests/test_v2_fixtures_command_executor.py`
- `tests/test_v2_fixtures_pipeline_executor.py`
- `tests/test_v2_fixtures_integration.py`

## Acceptance criteria fixed by this suite

- stable loader/import/base-dir semantics
- validator checks for callable collisions, imported-root restrictions, and forward local references
- expression/renderer behavior for namespaces, interpolation, escaping, built-ins, and function restrictions
- context/profile/locals semantics, including imported locals and bindings
- argv DSL serialization shape and invalid-shape errors
- command/pipeline executor runtime semantics (`when`, `continue_on_error`, `on_error`, `foreach`, timeout, env/workdir/runtime overrides, stream modes)

## Intentionally not covered in this step

- AppV2 UI behavior and launcher UI wiring
- persistence/presets/state
- parallel execution
- `param_imports`
- deep external-tool integrations (`yt-dlp`, `ffmpeg`, powershell)
