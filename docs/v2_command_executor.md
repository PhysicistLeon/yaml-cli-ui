# v2 command executor (step 8)

This step implements execution of a **single** `command` from `yaml_cli_ui.v2`.

## Execution flow

`CommandExecution`:

1. evaluate `command.when`
2. if false -> return `StepResult(status=skipped)`
3. resolve program (`profile.runtimes` override lookup)
4. serialize argv via v2 argv DSL serializer
5. resolve workdir (`run.workdir` > `profile.workdir` > `None`)
6. build process env (`os.environ` + `profile.env` + `run.env`)
7. execute subprocess with `shell=False`
8. map outputs/exit code/timing to `StepResult`

## Runtime override

- `run.program` is treated as key for `context.profile.runtimes`.
- If key exists: use override executable path.
- If key missing: use literal `run.program`.

## Environment merge

Deterministic merge order:

1. `os.environ`
2. `profile.env`
3. `run.env`

`run.env` values are rendered against runtime context. Final env values must be scalar (`str`, `int`, `float`, `bool`) and are converted with `str(...)`.

## stdout/stderr modes

Supported stream modes (`stdout`, `stderr`):

- `capture` (default) — keep in-memory and store in `StepResult.stdout/stderr`
- `inherit` — pass-through to parent process; result fields are `None`
- `file:<path>` — render path and overwrite target file (no auto-creation of parent dirs)

## Exit code/status mapping

- exit code `0` -> `StepStatus.SUCCESS`
- non-zero exit code -> `StepStatus.FAILED` (normal execution result, no infrastructure exception)

## Timeout behavior

When `timeout_ms` is set and exceeded:

- return `StepResult(status=failed)`
- `error.type = "timeout"`
- `exit_code = None`
- include timing fields

## Intentionally not implemented in step 8

- pipeline executor
- foreach runtime
- on_error runtime
- launcher execution flow
- v1 UI integration or presets/state behavior
