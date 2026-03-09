# YAML CLI UI v2-lite specification

Status: current reference for implemented v2-lite behavior in this repository.

## 1) Scope

v2-lite defines a launcher-oriented YAML DSL for running CLI workflows from UI.

Implemented core blocks:

- `imports`
- `profiles`
- `params`
- `locals` (ordered)
- callable namespace (`commands` + `pipelines`)
- `launchers`
- steps (`use`, `foreach`)
- `on_error`
- `with_values` runtime binding model (YAML key: `with`)

## 2) Terminology

- **Profile**: named runtime defaults (`workdir`, `env`, `runtimes`).
- **Param**: user-facing root input schema.
- **Local**: computed root value (evaluated in order).
- **Command**: one process launch (`run`).
- **Run**: process spec (`program`, `argv`, `workdir`, `env`, etc.).
- **Pipeline**: ordered step list.
- **Launcher**: UI entrypoint that calls one callable.
- **Import**: alias -> path to another v2 document.
- **Callable namespace**: combined names from `commands` and `pipelines` (no collisions).
- **Step**: pipeline item; either short string callable or expanded object.
- **Foreach**: step kind that iterates list input.
- **on_error**: recovery steps for failed command/pipeline.
- **with_values**: internal model field for prebound values from YAML `with`.
- **Result model**: `StepResult` with status/output/error metadata.
- **Explicit namespaces**:
  - `$params`
  - `$locals`
  - `$profile`
  - `$steps`
  - `$run`
  - `$loop`
  - `$error`

## 3) Field tables

### 3.1 Root document

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `version` | yes | int (`2`) | Must be exactly `2`. |
| `imports` | no | map<string,string> | Alias -> relative path. |
| `profiles` | no | map<string,profile> | Optional profile set. |
| `params` | no | map<string,param> | Root input schema. |
| `locals` | no | map<string,any> | Evaluated in declaration order. |
| `commands` | no | map<string,command> | Callable definitions. |
| `pipelines` | no | map<string,pipeline> | Callable definitions. |
| `launchers` | yes | map<string,launcher> | UI entrypoints. |

### 3.2 Profile

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `workdir` | no | string | Default working dir. |
| `env` | no | map<string,string> | Profile env overlay. |
| `runtimes` | no | map<string,string> | Program alias resolution. |

### 3.3 Param

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `type` | yes | enum | e.g. `string`, `bool`, `filepath`, `dirpath`, `secret`, `kv_list`, `struct_list`. |
| `title` | no | string | UI label override. |
| `required` | no | bool | Required in dialog if no default/source. |
| `default` | no | any | Default value. |
| `options` | no | list<any> | For choice-like types. |
| `min` / `max` / `step` | no | number | Numeric constraints. |
| `must_exist` | no | bool | Path params existence hint. |
| `source` | no | enum | `env` / `vault` for secrets. |
| `env` | no | string | Env var name when `source: env`. |
| `key` | no | string | Vault key name when `source: vault`. |

### 3.4 Command

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `run` | yes | run | Exactly one process launch spec. |
| `title` / `info` | no | string | Metadata. |
| `when` | no | any | Skip when falsey. |
| `continue_on_error` | no | bool | Local recovery behavior. |
| `on_error` | no | on_error | Recovery steps. |

### 3.5 Run

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `program` | yes | string/template | May resolve through `profile.runtimes`. |
| `argv` | yes | list<argv-item> | No shell splitting. |
| `workdir` | no | string/template | Defaults to profile/workdir/current process cwd chain. |
| `env` | no | map<string,any> | Merged on top of OS + profile env. |
| `timeout_ms` | no | int | Timeout => failure. |
| `stdout` | no | string | Capture/inherit/file mode value. |
| `stderr` | no | string | Capture/inherit/file mode value. |

### 3.6 Pipeline

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `steps` | yes | list<step> | Ordered execution. |
| `title` / `info` | no | string | Metadata. |
| `when` | no | any | Skip when falsey. |
| `continue_on_error` | no | bool | Local recovery behavior. |
| `on_error` | no | on_error | Recovery steps. |

### 3.7 Launcher

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `title` | yes | string | Button label. |
| `use` | yes | string | Callable ref. |
| `info` | no | string | Help/tooltip text. |
| `with` | no | map<string,any> | Read-only prebound values; model field name is `with_values`. |

### 3.8 Step (expanded)

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `step` | no | string | Optional explicit step id. |
| `when` | no | any | Skip step when falsey. |
| `continue_on_error` | no | bool | Continue parent flow after failure. |
| `use` | xor | string | Callable ref for use-step. |
| `foreach` | xor | foreach | Foreach spec for foreach-step. |
| `with` | no | map<string,any> | Binding map for called step. |

### 3.9 Foreach

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `in` | yes | any | Must evaluate to list. |
| `as` | yes | string | Item alias in `$loop`. |
| `steps` | yes | list<step> | Nested sequence for each item. |

### 3.10 on_error

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `steps` | yes | list<step> | Recovery steps run on owner failure. |

## 4) EBNF-like grammar (minimal)

```ebnf
document       = "version: 2", [imports], [profiles], [params], [locals],
                 [commands], [pipelines], launchers ;

imports        = "imports:", map(alias -> path) ;
commands       = "commands:", map(name -> command) ;
pipelines      = "pipelines:", map(name -> pipeline) ;
launchers      = "launchers:", non-empty-map(name -> launcher) ;

command        = [meta], "run:", run, ["on_error:", on_error] ;
run            = "program:", scalar, "argv:", list(argv_item),
                 ["workdir:", scalar], ["env:", map], ["timeout_ms:", int] ;

pipeline       = [meta], "steps:", list(step), ["on_error:", on_error] ;
launcher       = "title:", string, "use:", callable_ref, ["with:", map] ;

step           = callable_ref
               | { ["step:" string], ["when:" expr], ["continue_on_error:" bool],
                   "use:" callable_ref, ["with:" map] }
               | { ["step:" string], ["when:" expr], ["continue_on_error:" bool],
                   "foreach:", foreach } ;

foreach        = { "in:" expr, "as:" ident, "steps:", list(step) } ;
on_error       = { "steps:", list(step) } ;

argv_item      = scalar
               | option_map
               | { "when:", expr, "then:", (scalar | option_map) } ;
option_map     = { option_key: value } ;
```

## 5) Execution pseudocode

```text
load doc path
resolve imports graph recursively
validate root + imports constraints
select profile (UI selection/default)
evaluate imported locals
build base context ($params, $profile, imported locals)
evaluate root locals in order
build runtime context with launch bindings
execute launcher.use callable

execute command:
  evaluate command.when
  render run fields
  serialize argv without shell splitting
  run subprocess
  on failure -> execute on_error (if present)

execute pipeline:
  evaluate pipeline.when
  for step in steps:
    if step kind == use: execute callable with merged bindings
    if step kind == foreach:
      evaluate foreach.in (must be list)
      for each item: set $loop and run nested steps
    apply continue_on_error behavior
  on pipeline failure -> execute on_error (if present)

result model:
  produce StepResult for each executed/skipped/recovered step
  expose statuses: success | failed | skipped | recovered
```


## 6) Compatibility and routing facts (implemented)

- App routing is version-based at config open time:
  - `version: 1` -> legacy app stack
  - `version: 2` -> `AppV2` + v2 core
- v2 persistence filenames are:
  - `<config>.launchers.presets.json`
  - `<config>.state.json`
- Imported v2 docs are restricted to reusable library sections:
  - allowed: `locals`, `commands`, `pipelines`
  - forbidden: `profiles`, `launchers`
- Root/import locals are evaluated in declaration order; forward local references fail validation.
- Callable namespace must be collision-free across `commands` and `pipelines`.
- YAML key `with` maps to internal model field `with_values`.
- Step result statuses are: `success`, `failed`, `skipped`, `recovered`.

## 7) YAML pitfalls and practical workarounds

- `yes/no/on/off` can be parsed as booleans by YAML 1.1 style loaders; quote when string is intended.
- Windows paths should be quoted (e.g. `"C:\\tools\\python.exe"`) to avoid escape/colon ambiguity.
- Strings containing `:` should be quoted (`"a:b"`) to avoid accidental map parsing.
- Inline maps in argv are DSL objects, not free-form JSON; keep them small and explicit.
- Escape dollar literals with `$$` or `$${...}` when literal `$` is needed.
- YAML anchors/aliases are loader features only; they are not first-class DSL semantics.

## 8) Known limitations / intentionally deferred

- No `parallel` execution block.
- No `param_imports` model.
- No automatic v1 -> v2 config converter.
- No automatic v1 -> v2 persistence converter.
- Imported docs must not define `launchers` or `profiles`.
- Pipeline-level locals are intentionally unsupported.
- Foreach result addressing remains intentionally compact (no rich public aggregate API yet).
