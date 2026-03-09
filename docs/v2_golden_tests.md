# V2 Golden Tests and Fixtures

Этот слой фиксирует согласованное поведение v2-lite core через small-fixture golden tests.

## Fixture suite (`tests/fixtures/v2/`)

- Loader/imports: `minimal_root.yaml`, `with_imports_root.yaml`, `packs/media.yaml`, `packs/fs.yaml`.
- Locals/context: `valid_locals.yaml`, `invalid_future_local.yaml`.
- Argv DSL: `argv_mixed.yaml`.
- Pipeline/execution: `pipeline_success.yaml`, `pipeline_continue_on_error.yaml`, `pipeline_on_error_recovered.yaml`, `foreach_success.yaml`, `foreach_invalid_input.yaml`.
- Validator negative cases: `invalid_callable_collision.yaml`, `invalid_imported_with_launchers_root.yaml`, `packs/invalid_import_with_launchers.yaml`.
- Integration-like smoke: `full_ingest_like.yaml`.

## Covered layers

- `tests/test_v2_fixtures_loader.py`: загрузка root/imported docs, recursive imports, relative path resolution.
- `tests/test_v2_fixtures_validator.py`: key validation failures (locals ordering, callable collision, forbidden imported launchers).
- `tests/test_v2_fixtures_expr_renderer.py`: references, interpolation, escaping (`$$`, `$${`), ambiguity errors, allowlisted функции (`len`, `empty`, `exists`) и disallowed functions.
- `tests/test_v2_fixtures_context.py`: sequential locals, imported locals, profile selection, bindings merge semantics.
- `tests/test_v2_fixtures_argv.py`: scalar/mixed argv serialization и invalid argv shapes.
- `tests/test_v2_fixtures_command_executor.py`: command execution statuses, timeout, streams modes, workdir/runtime/env behavior.
- `tests/test_v2_fixtures_pipeline_executor.py`: success/failure/continue_on_error/foreach/on_error paths + smoke execution for `full_ingest_like.yaml`.

## Acceptance semantics fixed by tests

GoldenTest pattern:
- Given fixture/config
- When loading/rendering/executing one specific layer
- Then assert exact или structured semantic behavior.

Allowed assertion styles:
- exact equality
- structured field assertions
- explicit exception assertions

## Intentionally not covered on this step

- AppV2 UI behavior
- persistence/presets/state
- parallel
- param_imports
- advanced external addressing for foreach aggregation
- dependency on external tools (`yt-dlp`, `ffmpeg`, `powershell`) beyond portable `python -c`
