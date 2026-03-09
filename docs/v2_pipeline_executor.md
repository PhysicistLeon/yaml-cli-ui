# V2 pipeline executor (step 9)

This step adds runtime execution for `PipelineDef` in v2.

## Supported behavior

- Sequential pipeline execution in declared `steps` order.
- Step shapes:
  - short callable reference (`"hello"`, `"media.fetch"`)
  - expanded `use` step (`use` + optional `step`/`with`/`when`/`continue_on_error`)
  - `foreach` step (`foreach.in`, `foreach.as`, `foreach.steps`)
- Nested pipelines (a step may resolve to `PipelineDef`).
- `continue_on_error` for step and callable definitions.
- `on_error` for commands and pipelines.
- Runtime `$steps` tree is filled incrementally with each step result.

## Naming rule for short steps

For short syntax, default step name is the callable basename:
- `hello` -> `hello`
- `media.fetch_and_download` -> `fetch_and_download`

If the name is already used in current pipeline, a numeric suffix is added:
- `fetch_and_download_2`, `fetch_and_download_3`, ...

## `foreach` result shape

`foreach` returns a `StepResult` with:
- `children`: per-iteration results under `iter_0`, `iter_1`, ...
- `meta.iteration_count`
- `meta.success_count`
- `meta.failed_count`

Loop variables available inside each iteration:
- `$<as_name>` (item variable)
- `$loop.index`
- `$loop.first`
- `$loop.last`

## `on_error`

- Failed command/pipeline may execute `on_error.steps`.
- If recovery succeeds: owner status becomes `recovered`.
- If recovery fails: owner remains `failed`, with recovery info in `meta.recovery_error`.

## Intentionally not implemented in this step

- Parallel execution.
- Launcher flow wiring / AppV2 wiring.
- Presets/state persistence.
- UI integration.
