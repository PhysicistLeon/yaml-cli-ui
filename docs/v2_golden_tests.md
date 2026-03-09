# v2 golden fixtures and regression tests

This document captures the step-10 golden test suite for `yaml_cli_ui.v2`.

## Fixture suite (`tests/fixtures/v2`)

- Loader/import basics: `minimal_root.yaml`, `with_imports_root.yaml`, `packs/media.yaml`, `packs/fs.yaml`
- Loader negatives: `invalid_missing_import_root.yaml`, `invalid_import_cycle_root.yaml`, `packs/cycle_a.yaml`, `packs/cycle_b.yaml`
- Locals/context: `valid_locals.yaml`, `invalid_future_local.yaml`
- Argv DSL: `argv_mixed.yaml`
- Pipeline/executor flows: `pipeline_success.yaml`, `pipeline_continue_on_error.yaml`, `pipeline_on_error_recovered.yaml`, `foreach_success.yaml`, `foreach_invalid_input.yaml`
- Validator negatives: `invalid_callable_collision.yaml`, `invalid_imported_with_launchers_root.yaml`, `packs/invalid_import_with_launchers.yaml`, `invalid_imported_with_profiles_root.yaml`, `packs/invalid_import_with_profiles.yaml`
- Integration-like smoke case: `full_ingest_like.yaml`

Fixtures intentionally use portable Python snippets; tests may also use fixture placeholder replacement (for example `__PYTHON__` / `__TMPDIR__`) via `tests.v2_test_utils.load_fixture_document(..., replacements=...)`.

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

- stable loader/import/base-dir semantics, including missing-import and import-cycle failures
- validator checks for callable collisions, imported-root restrictions (`launchers`/`profiles`), and forward local references
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
