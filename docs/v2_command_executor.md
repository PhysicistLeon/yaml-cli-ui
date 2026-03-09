# v2 command executor (step 8)

This step implements execution of **one `command`** from `yaml_cli_ui/v2`.

## What is implemented

- `execute_command_def(command, context, step_name=...)` for a single command.
- `execute_run_spec(run_spec, context, step_name)` for direct run-spec execution.
- runtime override lookup from `profile.runtimes` via `resolve_program`.
- workdir resolution via `resolve_workdir`.
- env merge via `build_process_env`.
- stream routing modes for `stdout` and `stderr`:
  - `capture` (default)
  - `inherit`
  - `file:<path>`
- timeout handling with `StepResult(status=failed, error.type="timeout")`.
- `CommandDef.when` short-circuit to `StepResult(status=skipped)`.

## Execution flow (EBNF-aligned)

```text
CommandExecution :=
  if when == false -> skipped result
  else
    resolve program
    serialize argv
    resolve workdir
    build env
    execute subprocess
    collect stdout/stderr/exit_code/timing
    map to StepResult

StdStreamMode :=
    "capture"
  | "inherit"
  | "file:" path

ResultStatus :=
    success
  | failed
  | skipped
```

## Runtime override behavior

- If `run.program` is key in `context["profile"]["runtimes"]`, override is used.
- Otherwise `run.program` is used literally.

## Environment merge behavior

Process env is built as:

1. `os.environ`
2. merged with `profile.env`
3. merged with `run.env` (rendered values)

`run.env` rendered values must be scalar string/number/bool and are stringified.

## Exit/result mapping

- exit code `0` -> `StepStatus.SUCCESS`
- non-zero exit code -> `StepStatus.FAILED` (no infrastructure exception)
- timeout -> `StepStatus.FAILED` + timeout error context
- `when=false` -> `StepStatus.SKIPPED`

## Intentionally not implemented in this step

- pipeline executor
- foreach runtime
- on_error runtime
- launcher execution flow
- UI wiring
- presets/state
- parallel execution
