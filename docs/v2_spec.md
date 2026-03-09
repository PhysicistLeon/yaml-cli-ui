# v2-lite specification (final reference)

Status: current reference for `version: 2` documents in this repository.

## 1) Terminology

- **profile**: named runtime defaults (`workdir`, `env`, `runtimes`).
- **param**: user-editable input schema in root `params`.
- **local**: root-level computed value in ordered `locals`.
- **command**: callable that wraps one `run` process launch.
- **pipeline**: callable with ordered `steps`.
- **launcher**: UI entrypoint (`title`, `use`, optional `with`).
- **import**: named alias to another v2 document.
- **callable namespace**: local + imported callable names (`name` / `alias.name`).
- **step**: pipeline item, either simple callable string or expanded map.
- **foreach**: special expanded step with `in`, `as`, `steps`.
- **on_error**: recovery block for failed command/pipeline.
- **with_values**: internal model field for YAML key `with` bindings.
- **result model**: `StepResult` records (`status`, `exit_code`, `stdout`, `stderr`, `error`, nested results).

Explicit namespaces available in expressions/templates:

- `$params`
- `$locals`
- `$profile`
- `$steps`
- `$run`
- `$loop`
- `$error`

## 2) Root and section field tables

### Root document

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `version` | yes | int | Must be `2`. |
| `imports` | no | map<string,string> | Alias -> relative file path. |
| `profiles` | no | map | Named execution profiles. |
| `params` | no | map | Root input schema. |
| `locals` | no | map | Ordered evaluated locals. |
| `commands` | no | map | Command callables. |
| `pipelines` | no | map | Pipeline callables. |
| `launchers` | yes (root) | map | Root UI entrypoints, non-empty. |

Imported documents may contain only: `imports`, `locals`, `commands`, `pipelines`.

### Profile

| Field | Required | Type |
| --- | --- | --- |
| `workdir` | no | string |
| `env` | no | map<string,string> |
| `runtimes` | no | map<string,string> |

### Param

| Field | Required | Type |
| --- | --- | --- |
| `type` | yes | enum (`string`, `text`, `bool`, `int`, `float`, `choice`, `multichoice`, `filepath`, `dirpath`, `secret`, `kv_list`, `struct_list`) |
| `title` | no | string |
| `required` | no | bool |
| `default` | no | any |
| `options` | conditional | list |
| `min` / `max` / `step` | conditional | number |
| `must_exist` | conditional | bool |
| `source` / `env` / `key` | conditional | string (`secret`) |
| `item_schema` | conditional | map (`struct_list`) |

### Command

| Field | Required | Type |
| --- | --- | --- |
| `run` | yes | run block |
| `title` | no | string |
| `info` | no | string |
| `when` | no | expression/template |
| `continue_on_error` | no | bool |
| `on_error` | no | on_error block |

### Run

| Field | Required | Type |
| --- | --- | --- |
| `program` | yes | string/template |
| `argv` | no | list<argv-item> |
| `workdir` | no | string/template |
| `env` | no | map<string,string/template> |
| `timeout_ms` | no | int |
| `stdout` | no | string |
| `stderr` | no | string |

### Pipeline

| Field | Required | Type |
| --- | --- | --- |
| `steps` | yes | list<step> |
| `title` | no | string |
| `info` | no | string |
| `when` | no | expression/template |
| `continue_on_error` | no | bool |
| `on_error` | no | on_error block |

### Launcher

| Field | Required | Type |
| --- | --- | --- |
| `title` | yes | string |
| `use` | yes | callable ref |
| `info` | no | string |
| `with` | no | map<string,any/template> |

### Step (expanded)

| Field | Required | Type |
| --- | --- | --- |
| `step` | no | string |
| `when` | no | expression/template |
| `continue_on_error` | no | bool |
| `use` | xor | callable ref |
| `with` | no | map<string,any/template> |
| `foreach` | xor | foreach block |

### Foreach

| Field | Required | Type |
| --- | --- | --- |
| `in` | yes | expression/template resolving list |
| `as` | yes | string |
| `steps` | yes | list<step> |

### on_error

| Field | Required | Type |
| --- | --- | --- |
| `steps` | yes | list<step> |

## 3) Minimal EBNF-like grammar

```text
document        := version imports? profiles? params? locals? commands? pipelines? launchers
imports         := "imports" ":" map(alias -> filepath)
command         := "commands" ":" map(name -> command_def)
command_def     := title? info? when? continue_on_error? run on_error?
run             := "run" ":" program argv? workdir? env? timeout_ms? stdout? stderr?
pipeline        := "pipelines" ":" map(name -> pipeline_def)
pipeline_def    := title? info? when? continue_on_error? "steps" ":" [step+] on_error?
launcher        := "launchers" ":" map(name -> launcher_def)
launcher_def    := "title" ":" str, "use" ":" callable_ref, info?, with?
step            := string_callable_ref | expanded_step
expanded_step   := step_name? when? continue_on_error? (use_step | foreach_step)
use_step        := "use" ":" callable_ref, with?
foreach_step    := "foreach" ":" foreach_block
foreach_block   := "in" ":" expr, "as" ":" name, "steps" ":" [step+]
argv_item       := scalar | option_map | conditional_item
option_map      := { "--flag": value }
conditional_item:= { "when": expr, "then": (scalar | option_map | list) }
```

## 4) Execution pseudocode

```text
1. load doc from YAML
2. resolve imports graph (alias -> document), detect cycles
3. validate root/import constraints and schema
4. choose profile (UI/default selection)
5. evaluate imported locals then root locals (ordered)
6. build runtime context namespaces
7. execute launcher.use callable with launcher.with bindings
8. command execution:
   - evaluate command.when; skip if false
   - render run.program/argv/workdir/env
   - resolve runtime alias from selected profile.runtimes
   - subprocess.run(shell=False)
   - build StepResult
9. pipeline execution:
   - evaluate pipeline.when; skip if false
   - execute steps sequentially
10. foreach step:
   - resolve foreach.in to iterable
   - set $loop context for each item
   - execute nested steps
11. on_error:
   - when command/pipeline fails, populate $error and execute recovery steps
   - recovered result is marked accordingly
12. return result model tree to UI/log renderer/persistence consumers
```

## 5) YAML pitfalls and safe practices

- YAML booleans: quote values like `"yes"`, `"no"`, `"on"`, `"off"` when string semantics are needed.
- Windows paths: quote backslash paths (`"C:\\tmp\\a.txt"`).
- Strings with `:` should be quoted (`"name: value"`).
- Prefer block maps over dense inline maps for readability/debuggability.
- Escape `$` in templates with `$$` and `$${` when literal dollars are needed.
- YAML anchors/aliases are parser features, not DSL semantics; avoid depending on them for callable behavior.

## 6) Known limitations / intentionally deferred

- no `parallel` execution mode;
- no `param_imports` merge model;
- no auto-migration from v1 config/storage;
- no import of `launchers`, `profiles`, `params` from library packs;
- no pipeline-level locals section;
- foreach public result addressing is intentionally limited to current runtime model.
