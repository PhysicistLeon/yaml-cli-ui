# V2 Pipeline Executor (Step 9)

## What is implemented

- Sequential execution of `PipelineDef.steps`.
- Step forms:
  - short callable ref (`"name"`, `"alias.name"`)
  - expanded `use` step (`step/when/use/with/continue_on_error`)
  - `foreach` step (`foreach.in/as/steps`)
- Nested pipelines via callable resolution.
- `continue_on_error` on command/pipeline/step levels.
- `on_error` on command and pipeline levels.
- Incremental `$steps` updates after each executed step.

## Callable resolution

- Local namespace: `commands + pipelines` in one callable namespace.
- Imported namespace: `alias.callable_name` resolved against `imported_documents[alias]`.

## Step naming rules

- Short step name defaults to callable tail (`media.fetch` -> `fetch`).
- If name already exists, `_2`, `_3`, ... suffix is used (`fetch_2`).

## `with` + `when` semantics

- For expanded `use` steps, `with` bindings are applied before `when` evaluation.
- `with` values participate in short-name resolution through both:
  - `bindings` namespace
  - top-level short-name keys in child context
- Explicit namespaces are stable and not overridden:
  - `$params.*` always refers to root params
  - `$locals.*` always refers to evaluated locals

## `foreach` behavior

- `foreach.in` is rendered/evaluated in runtime context and must be a list.
- Per iteration context includes:
  - item variable from `as`
  - `loop.index`, `loop.first`, `loop.last`
  - root namespaces (`params`, `locals`, `profile`, `run`, `steps`) preserved
- Iteration results are stored in `children` as `iter_0`, `iter_1`, ...
- Aggregates are written to `meta`:
  - `iteration_count`
  - `success_count`
  - `failed_count`

## Error behavior

- Command non-zero exit -> failed `StepResult` (no exception).
- Runtime/config issues (e.g. unresolved callable, invalid foreach input) -> `V2ExecutionError`.
- Pipeline-level `on_error` runs only on hard stop failure (not on end-of-pipeline soft failures from `continue_on_error`).
- Recovery pipeline result keeps normal status (`success`/`failed`), while owner result becomes `recovered` on successful recovery.
- On failed recovery, owner keeps primary error in `error`, and recovery details are stored in `meta["recovery_error"]`.

## Intentionally not implemented in this step

- Parallel execution.
- Launcher execution flow.
- AppV2 wiring/UI integration.
- Preset/state/persistence layers.
