# YAML CLI Workflow DSL v2-lite — Draft 1

Status: Draft 1 (normative for backlog step 1).

This document is the single source of truth for implementing the v2-lite parser, validator, renderer, executor, and AppV2 integration. It is self-contained and does not rely on source-code behavior.

---

## 1) Goal and scope

The DSL defines a GUI wrapper over CLI workflows.

The DSL MUST support:

- loading a root YAML document;
- rendering UI entrypoints from `launchers`;
- collecting user inputs from root `params`;
- computing internal values from `locals`;
- launching external processes from `commands`;
- composing sequential workflows with `pipelines`;
- reusing configuration through `imports`;
- iterative execution through `foreach`;
- recovery through `on_error`;
- safe argv serialization without shell splitting.

This draft intentionally excludes: `parallel`, imported params merge model (`param_imports`), rich public per-iteration foreach result addressing, pipeline-level locals.

---

## 2) Terminology

- **Root document**: the top-level YAML file chosen by UI.
- **Imported document**: a YAML file loaded via `imports` from another document.
- **Namespace**: import alias used to access imported entities (for example `media.fetch`).
- **Callable**: executable DSL entity; one of `command` or `pipeline`.
- **Profile**: selected runtime environment (`workdir`, `env`, `runtimes`).
- **Param**: user-provided root input definition in `params`.
- **Local**: computed internal value defined in document-level `locals`.
- **Launcher**: UI-only entrypoint that targets exactly one callable.
- **Command**: definition of one external process launch.
- **Pipeline**: ordered sequence of steps; may call commands/pipelines/foreach.
- **Step**: one item in `pipeline.steps`.
- **Foreach step**: special step that iterates over list input.
- **Run block**: process execution spec inside a command (`program`, `argv`, etc.).
- **Argv item**: one entry in argv DSL (`scalar`, `option-map`, `conditional`).
- **Context**: name/value environment available for expressions/templates.
- **Step result**: structured output/status recorded for a step.
- **on_error**: recovery block executed when command/pipeline fails.

---

## 3) Top-level document structure

```yaml
version: 2

imports: {}
profiles: {}
params: {}
locals: {}
commands: {}
pipelines: {}
launchers: {}
```

### 3.1 Required fields

- `version` MUST exist and MUST be `2`.
- `launchers` MUST exist in the root document and MUST be a non-empty map.

### 3.2 Optional fields

- `imports`, `profiles`, `params`, `locals`, `commands`, `pipelines`.

### 3.3 Imported document constraints

Imported documents MAY contain only:

- `imports`, `locals`, `commands`, `pipelines`.

Imported documents MUST NOT define:

- `profiles`, `launchers`, `params`.

---

## 4) Field tables

### 4.1 Profile

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| workdir | no | string | process cwd fallback | Base working directory. |
| env | no | map<string,string> | `{}` | Merged into process env. |
| runtimes | no | map<string,string> | `{}` | Runtime alias map (e.g. `python`). |

### 4.2 Param

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| type | yes | enum | — | One of: string, text, bool, int, float, choice, multichoice, filepath, dirpath, secret, kv_list, struct_list. |
| title | no | string | param id | UI label. |
| required | no | bool | false | Required user input. |
| default | no | any | none | See lifecycle rules; only literals/profile refs allowed. |
| min/max/step | no | number | none | Numeric params. |
| options | no | list | none | `choice` / `multichoice`. |
| must_exist | no | bool | false | `filepath` / `dirpath`. |
| source/env/key | conditional | strings | none | `secret` source config. |
| item_schema | conditional | map | none | `struct_list` item schema. |

### 4.3 Command

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| title | no | string | none | UI/description metadata. |
| info | no | string | none | Extra description. |
| when | no | expression/template | true | If false => `skipped`. |
| continue_on_error | no | bool | false | Failure does not stop parent pipeline. |
| run | yes | run block | — | One command = one process launch. |
| on_error | no | recovery block | none | Runs on command failure. |

### 4.4 Run block

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| program | yes | string/template | — | May resolve through `profile.runtimes.<name>`. |
| argv | yes | list<argv-item> | — | No shell splitting. |
| workdir | no | string/template | `profile.workdir` else process cwd | Working dir. |
| env | no | map<string,string/template> | `{}` | Merge order: OS -> profile -> run. |
| timeout_ms | no | int | none | Timeout => failure type `timeout`. |
| stdout | no | enum | `capture` | `capture`, `inherit`, `file:<path>`. |
| stderr | no | enum | `capture` | `capture`, `inherit`, `file:<path>`. |

### 4.5 Pipeline

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| title | no | string | none | Metadata. |
| info | no | string | none | Metadata. |
| when | no | expression/template | true | If false => pipeline-step `skipped`. |
| continue_on_error | no | bool | false | Failure does not stop parent pipeline. |
| steps | yes | list<step> | — | Ordered execution. |
| on_error | no | recovery block | none | Runs on pipeline failure. |

### 4.6 Expanded step

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| step | no | string | generated | Step id/name used in logs/results. |
| when | no | expression/template | true | If false => skipped. |
| use | yes | callable ref | — | May point to command or pipeline. |
| with | no | map<string,any/template> | `{}` | Bound names in step scope. |
| continue_on_error | no | bool | false | Continue parent pipeline on failure. |

### 4.7 Foreach block

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| in | yes | expression/template | — | MUST evaluate to list at runtime. |
| as | yes | string | — | Current item alias. |
| steps | yes | list<step> | — | Nested step sequence per item. |

### 4.8 Launcher

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| title | yes | string | — | UI label. |
| info | no | string | none | UI help text. |
| use | yes | callable ref | — | Command or pipeline target. |
| with | no | map<string,any/template> | `{}` | Prebound read-only values. |

### 4.9 Step result

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| status | yes | enum | — | success/failed/skipped/recovered. |
| exit_code | yes | int\|null | null | Non-process steps may keep null. |
| stdout | yes | string\|null | null | Captured output or null. |
| stderr | yes | string\|null | null | Captured output or null. |
| duration_ms | yes | int | — | Execution duration. |
| started_at | yes | datetime string | — | Start time. |
| finished_at | yes | datetime string | — | End time. |

### 4.10 Error context (`$error.*`)

| name | required? | type | default | notes |
| --- | --- | --- | --- | --- |
| step | yes | string | — | Failed step identifier. |
| type | yes | string | — | Error type/category. |
| message | yes | string | — | Human-readable message. |
| exit_code | no | int\|null | null | Present for process failures when available. |

---

## 5) EBNF-like grammar (pseudo)

```ebnf
document          = "version" ":" 2, doc-sections ;
doc-sections      = [imports], [profiles], [params], [locals],
                    [commands], [pipelines], launchers ;

imports           = "imports" ":" map(alias -> path-string) ;
profiles          = "profiles" ":" map(profile-name -> profile-def) ;
params            = "params" ":" map(param-name -> param-def) ;
locals            = "locals" ":" map(local-name -> template-or-scalar) ;
commands          = "commands" ":" map(callable-name -> command-def) ;
pipelines         = "pipelines" ":" map(callable-name -> pipeline-def) ;
launchers         = "launchers" ":" non-empty-map(launcher-name -> launcher-def) ;

command-def       = { [title], [info], [when], [continue_on_error], run, [on_error] } ;
run               = "run" ":" { program, argv, [workdir], [env], [timeout_ms], [stdout], [stderr] } ;

pipeline-def      = { [title], [info], [when], [continue_on_error], steps, [on_error] } ;
steps             = "steps" ":" list(step-item) ;
step-item         = short-callable-step | expanded-use-step | foreach-step ;
short-callable-step = callable-ref-string ;
expanded-use-step = { [step], [when], use, [with], [continue_on_error] } ;
foreach-step      = { [step], "foreach" ":" foreach-block, [when], [continue_on_error] } ;
foreach-block     = { "in": expr-or-template, "as": identifier, "steps": list(step-item) } ;

argv              = "argv" ":" list(argv-item) ;
argv-item         = scalar-item | option-map | conditional-item ;
scalar-item       = scalar-or-template ;
option-map        = "{" option-key ":" value-expr "}" ;
conditional-item  = "{" "when" ":" expr-or-template "," "then" ":" (scalar-item | option-map) "}" ;

template          = "$" short-name | "${" expression "}" ;
reference         = explicit-reference | short-name ;
explicit-reference =
    "params." path | "locals." path | "profile." path | "run." path |
    "steps." path | "loop." path | "error." path | import-ns ".locals." path ;
expression        = allowlisted-safe-expression ;
```

---

## 6) Syntax rules

### 6.1 Imports syntax

```yaml
imports:
  fs: ./packs/fs.yaml
  media: ./packs/media.yaml
```

### 6.2 Command syntax

```yaml
commands:
  scrape_source:
    run:
      program: python
      argv:
        - scripts\scrape_source.py
        - { --source: $params.source_url }
```

### 6.3 Pipeline syntax

```yaml
pipelines:
  ingest_single:
    steps:
      - media.fetch_and_download
      - step: import_db
        use: db.import_and_cleanup
```

### 6.4 Foreach syntax

```yaml
- step: per_job
  foreach:
    in: $params.jobs
    as: job
    steps:
      - use: ingest_single
        with:
          source_url: $job.source_url
```

### 6.5 Launcher syntax

```yaml
launchers:
  ingest_single:
    title: Ingest single
    use: ingest_single
```

---

## 7) Semantics

### 7.1 Imports

1. Import paths MUST be resolved relative to the declaring document file.
2. Import graph MUST be acyclic.
3. Imported docs MAY contain only `imports`, `locals`, `commands`, `pipelines`.
4. `profiles`, `launchers`, `params` from imported docs are forbidden and not imported.
5. Imported symbols are available as:
   - `ns.locals.*`
   - `ns.<command_name>`
   - `ns.<pipeline_name>`

### 7.2 Namespaces and callables

1. Inside one document, `commands` and `pipelines` share one callable namespace.
2. Duplicate names across command/pipeline in same document are fatal config errors.
3. Explicit namespaces MUST be supported:
   - `$params.x`, `$locals.x`, `$profile.x`, `$steps.s.x`, `$loop.index`, `$run.id`, `$error.message`, `$ns.locals.x`.

### 7.3 Local values

1. Pipeline-level locals are NOT supported.
2. Locals are document-level only.
3. Locals MUST be evaluated in declaration order (top-to-bottom) inside each document.
4. Allowed references from local:
   - `params.*`, `profile.*`, `run.*`,
   - previously declared `locals.*` in same document,
   - explicit imported `ns.locals.*`.
5. Forbidden references from local:
   - future locals,
   - `steps.*`, `loop.*`, `error.*`,
   - `with` bindings.
6. Root locals MAY reference imported `ns.locals.*`.
7. Imported locals MUST NOT reference root `locals.*`.

### 7.4 Expressions

Allowed:

- literals (`null`, bool, numbers, strings),
- parentheses,
- comparisons (`== != < > <= >=`),
- logical ops (`and`, `or`, `not`),
- dot/index access,
- functions: `len(x)`, `empty(x)`, `exists(path)`.

Forbidden:

- arbitrary function calls,
- lambda/comprehensions/import/exec/eval,
- any AST node outside allowlist.

Implementation MUST use safe AST allowlist evaluator.

### 7.5 Template rendering

Supported forms:

- short ref: `$name`
- explicit ref: `$params.name`, `$run.id`, etc.
- expression interpolation: `${expr}`

Escaping:

- `$$` => literal `$`
- `$${` => literal `${`

Expected behavior:

1. If string is exactly one reference token (for example `$params.x`), result is typed value.
2. `${expr}` inside larger string is string-interpolated.
3. `null` interpolation yields empty string.
4. Renderer algorithm SHOULD:
   - protect escaped literals,
   - evaluate refs/expressions,
   - restore protected literals.

### 7.6 argv DSL

Allowed argv item shapes:

1. scalar item,
2. option map `{ --flag: value }`,
3. conditional item `{ when: EXPR, then: ITEM }`.

Serialization rules:

- scalar => exactly one argv token;
- option map value `true` => append key only;
- `false` / `null` / `""` => omit;
- scalar => append `[key, str(value)]`;
- list => append repeated `[key, str(item)]`;
- empty list => omit;
- numeric `0` is NOT empty and MUST serialize as `"0"`;
- string `"false"` is a regular string and MUST NOT be treated as bool false.

Invalid shape example (MUST fail validation):

```yaml
- { when: $x, --audio-format: mp3 }
```

### 7.7 Command semantics

1. One command = one process launch.
2. `run` block is required.
3. `when=false` => step status `skipped`.
4. `continue_on_error=true` keeps parent pipeline running; step status remains `failed`.
5. `stdout`/`stderr` allowed values: `capture`, `inherit`, `file:<path>`.
6. Defaults: `stdout=capture`, `stderr=capture`.
7. Program runtime override MAY resolve `program: python` via `profile.runtimes.python`.
8. Environment merge order MUST be:
   - `os.environ`
   - `profile.env`
   - `run.env`

### 7.8 Pipeline semantics

1. Pipeline is ordered step sequence.
2. Step kinds: short callable ref, expanded use-step, foreach-step.
3. Expanded step fields: `step`, `when`, `use`, `with`, `continue_on_error`.
4. `use` in step and launcher MAY target command or pipeline.

### 7.9 Foreach semantics

1. `foreach.in` MUST evaluate to list at runtime.
2. `foreach.as` defines current item alias.
3. Inside foreach iteration available:
   - item alias,
   - `loop.index`, `loop.first`, `loop.last`.
4. v2-lite public foreach result is aggregate-only:
   - `status`, `duration_ms`, `iteration_count`, `success_count`, `failed_count`.

### 7.10 Results model

Each step result MUST include:

- `status`, `exit_code`, `stdout`, `stderr`, `duration_ms`, `started_at`, `finished_at`.

Allowed statuses: `success`, `failed`, `skipped`, `recovered`.

### 7.11 Error model

Categories:

- **fatal config error** (invalid YAML/DSL contract),
- **runtime error** (evaluation/execution-time failure),
- **step failure** (process exit non-zero, timeout, etc.).

Default behavior:

- step failure stops current pipeline,
- if `on_error` exists then recovery runs,
- if recovered successfully -> status `recovered`, else `failed` and both primary/recovery errors are retained.

### 7.12 Launchers

1. Launchers are UI entrypoints only.
2. Launcher fields: `title` (required), `info` (optional), `use` (required), `with` (optional).
3. Launcher `with` values are prebound read-only inputs.

### 7.13 Profiles

1. Exactly one profile MUST be selected per launcher run when profiles are declared.
2. Profile fields: `workdir`, `env`, `runtimes`.

### 7.14 Secrets

`secret` params support:

- `source: env` (`env` key required),
- `source: vault` (`key` required).

Security requirements:

- secrets MUST NOT be persisted in presets/state,
- secrets MUST be masked in logs/debug dumps.

---

## 8) Lifecycle: `run.id` and locals (normative)

1. `params.default` values are evaluated before launcher run allocation and MAY reference only:
   - literals,
   - `profile.*`.
2. `params.default` MUST NOT reference:
   - `locals.*`, `run.*`, `steps.*`, `loop.*`, `error.*`.
3. `run.id` and `run.started_at` MUST be created only after:
   - launcher selected,
   - profile selected,
   - params collected and validated.
4. One launcher run MUST have exactly one unique `run.id`.
5. Locals are computed only after `run` allocation.
6. Imported document locals MUST be computed before root locals.
7. Document locals evaluation order MUST follow import-graph topological order.
8. Inside a document, locals MUST be top-to-bottom.

Lifecycle pseudocode:

```text
load documents
resolve imports
validate schemas and names
choose profile
resolve param defaults
collect and validate params
allocate run.id / run.started_at
compute imported locals in import-topological order
compute root locals
execute launcher target
```

---

## 9) Formal short-name resolution order (normative)

### 9.1 Explicit references

If explicit namespace is written, it MUST be used directly:

- `$params.x`
- `$locals.x`
- `$profile.workdir`
- `$steps.scrape.stdout`
- `$loop.index`
- `$run.id`
- `$error.message`
- `$ns.locals.x`

### 9.2 Short-name fallback

Short `$name` is allowed only through this order:

1. current foreach alias (`as`),
2. accumulated `with` bindings (inner step overrides outer pipeline/launcher),
3. root params,
4. locals of current document.

### 9.3 Names never resolved by short fallback

The following MUST NOT resolve via short-name fallback:

- `profile`, `run`, `steps`, `loop`, `error`,
- imported locals from other documents.

Examples:

- `$profile.workdir` valid.
- `$run.id` valid.
- `$steps.scrape.stdout` valid.
- `$media.locals.script_path` valid.
- `$script_path` for imported local is invalid.

### 9.4 Shadowing and ambiguity

1. Foreach alias intentionally shadows all lower-priority sources.
2. `with` bindings intentionally shadow params and locals.
3. Params vs locals MUST NOT silently shadow each other.
   - If both contain same name and config uses `$name`, this is fatal ambiguity.
   - Explicit namespace is required.

| source | allowed in short names? | explicit namespace required? | can shadow? |
| --- | --- | --- | --- |
| foreach alias | yes | no | yes (highest) |
| with bindings | yes | no | yes (over params/locals) |
| root params | yes | no (unless ambiguous) | no silent shadow vs locals |
| current document locals | yes | no (unless ambiguous) | no silent shadow vs params |
| profile/run/steps/loop/error | no | yes | n/a |
| imported locals | no | yes (`$ns.locals.x`) | n/a |

---

## 10) Validation and execution phases

### Phase 1 — YAML parse

- YAML syntax parsing,
- imported file existence,
- raw YAML loading.

### Phase 2 — static config validation

- section presence/shape,
- import cycle detection,
- forbidden sections in imported docs,
- duplicate callable names,
- local forward-reference detection,
- invalid step forms,
- invalid argv item forms,
- unknown `use` targets,
- invalid expression syntax / forbidden AST nodes,
- reserved-name misuse.

### Phase 3 — launcher preflight

- selected profile existence,
- param default evaluation,
- param value validation,
- secret source readiness,
- launcher binding validation.

### Phase 4 — runtime execution

- locals evaluation,
- expression evaluation during steps,
- foreach input list validation,
- program resolution,
- argv serialization,
- subprocess execution,
- timeout handling,
- `must_exist` checks if runtime-dependent.

### Phase 5 — recovery execution

- `on_error` execution,
- `$error.*` context construction,
- recovery failures.

Summary matrix:

| Concern | Phase |
| --- | --- |
| YAML syntax | parse |
| import cycle | static validation |
| local future reference | static validation |
| selected profile missing | launcher preflight |
| secret env missing | launcher preflight |
| foreach.in not list | runtime execution |
| process timeout | runtime execution |
| on_error failure | recovery execution |

---

## 11) Error classification and earliest detection phase

Rule: “earliest phase” = earliest reliable phase for deterministic detection.

| error | category | earliest phase | who reports it (UI / engine) | notes |
| --- | --- | --- | --- | --- |
| YAML parse error | fatal config | parse | engine | malformed YAML syntax. |
| imported file not found | fatal config | parse | engine | import path unresolved. |
| import cycle | fatal config | static validation | engine | graph must be acyclic. |
| missing `launchers` in root | fatal config | static validation | engine | root-only required section. |
| forbidden `profiles` in imported doc | fatal config | static validation | engine | imported doc shape rule. |
| forbidden `launchers` in imported doc | fatal config | static validation | engine | imported doc shape rule. |
| duplicate callable name | fatal config | static validation | engine | command/pipeline namespace collision. |
| invalid param type | fatal config | static validation | engine | unknown type enum. |
| invalid run block | fatal config | static validation | engine | missing/invalid fields. |
| invalid step shape | fatal config | static validation | engine | not short/use/foreach form. |
| invalid foreach shape | fatal config | static validation | engine | missing `in/as/steps` fields. |
| invalid argv item | fatal config | static validation | engine | shape not scalar/option/conditional. |
| local refers to future local | fatal config | static validation | engine | within document order check. |
| unknown `use` target | fatal config | static validation | engine | callable resolution failure. |
| invalid expression syntax | fatal config | static validation | engine | parse-time AST syntax. |
| forbidden expression function | fatal config | static validation | engine | call not in allowlist. |
| ambiguous short `$name` (params vs locals) | fatal config | static validation | engine | deterministic ambiguity. |
| selected profile missing | runtime precondition | launcher preflight | UI and engine | UI selects; engine validates. |
| param required missing | runtime precondition | launcher preflight | UI and engine | UI validates; engine re-checks. |
| param type validation failure | runtime precondition | launcher preflight | UI and engine | UI validates; engine authoritative. |
| secret env var missing | runtime precondition | launcher preflight | UI and engine | `source: env`. |
| secret vault key unavailable | runtime precondition | launcher preflight | UI and engine | vault readiness failure. |
| locals evaluation failure | runtime error | runtime execution | engine | expression/render/type failure. |
| ambiguous short `$name` due to runtime with/foreach bindings | runtime error | runtime execution | engine | depends on active runtime scope. |
| foreach.in not list | runtime error | runtime execution | engine | validated after eval. |
| subprocess program not found | step failure | runtime execution | engine | OS launch error. |
| subprocess non-zero exit | step failure | runtime execution | engine | process completed with failure code. |
| timeout | step failure | runtime execution | engine | timeout policy violation. |
| on_error failure | recovery failure | recovery execution | engine | both primary/recovery errors retained. |

---

## 12) Fatal config errors (normative list)

The following MUST be treated as fatal config errors:

- `version != 2`,
- missing/empty root `launchers`,
- import cycles,
- unresolved relative import path,
- forbidden sections in imported docs,
- duplicate callable names in one document namespace,
- unknown `use`,
- invalid step shape,
- invalid argv item shape,
- local -> future local reference,
- ambiguous short `$name` where ambiguity is statically knowable,
- unknown expression function,
- forbidden AST node,
- invalid param type.

---

## 13) Execution pseudocode

### 13.1 `load_and_validate_document`

```text
function load_and_validate_document(root_path):
  root_doc = parse_yaml(root_path)
  docs = resolve_imports(root_doc, root_path)
  validate_schema_and_names(docs)
  validate_static_expressions(docs)
  return compiled_model(docs)
```

### 13.2 `resolve_imports`

```text
function resolve_imports(doc, doc_path):
  build directed graph by walking imports recursively
  resolve each import path relative to declaring doc directory
  fail on missing file
  fail on cycle
  return all loaded docs + topological order
```

### 13.3 `compute_locals`

```text
function compute_locals(topo_docs, root_doc, context):
  for each imported doc in topo_docs excluding root:
    eval locals top-to-bottom with document-scoped resolver
  eval root locals top-to-bottom
  return locals stores
```

### 13.4 `render_template`

```text
function render_template(value, resolver, evaluator):
  if value is not string: return value
  protect '$$' and '$${'
  resolve explicit refs and short refs
  evaluate '${expr}' segments
  map null -> '' for string interpolation
  restore protected literals
  return rendered value
```

### 13.5 `eval_expression`

```text
function eval_expression(expr, context):
  parse to AST
  ensure every node/function is allowlisted
  evaluate with safe evaluator
  return result
```

### 13.6 `execute_launcher`

```text
function execute_launcher(model, launcher_name, profile_name, input_params):
  launcher = resolve_launcher(launcher_name)
  profile = resolve_profile(profile_name)
  defaults = resolve_param_defaults(profile)
  params = validate_and_merge_params(defaults, input_params, launcher.with)
  run = allocate_run_metadata()  # run.id, run.started_at
  locals = compute_locals(import_topo_order, root_doc, {params, profile, run})
  return execute_step_target(launcher.use, launcher.with, {params, profile, run, locals})
```

### 13.7 `execute_pipeline`

```text
function execute_pipeline(pipeline, context):
  init step_results
  for step in pipeline.steps in order:
    result = execute_step(step, context, step_results)
    store result
    if result failed and not continue_on_error:
      return handle_pipeline_error(pipeline.on_error, context, result)
  return pipeline_success_result
```

### 13.8 `execute_step`

```text
function execute_step(step, context, step_results):
  normalize step form
  if step.when exists and eval false: return skipped
  if step is short/use: resolve callable and execute command/pipeline
  if step is foreach: return execute_foreach(step.foreach, context, step_results)
  else fail invalid step
```

### 13.9 `execute_command`

```text
function execute_command(command, context):
  if command.when exists and eval false: return skipped
  run_spec = command.run
  program = resolve_program(run_spec.program, context.profile.runtimes)
  argv = serialize_argv(run_spec.argv, context)
  env = merge_env(os.environ, profile.env, run_spec.env)
  workdir = resolve_workdir(run_spec.workdir, profile.workdir)
  proc_result = run_subprocess(program, argv, env, workdir, timeout_ms, stdout_mode, stderr_mode)
  if proc_result failed: return execute_on_error(command.on_error, context, proc_result.error)
  return success step result
```

### 13.10 `execute_foreach`

```text
function execute_foreach(foreach_def, context, step_results):
  items = eval(foreach_def.in)
  fail if items is not list
  aggregate counters
  for i, item in enumerate(items):
    iter_ctx = context + {alias=item, loop={index, first, last}}
    execute nested steps in iter_ctx
    update aggregate counters
  return aggregate foreach result
```

### 13.11 `execute_on_error`

```text
function execute_on_error(on_error_block, context, primary_error):
  if absent: return failed(primary_error)
  err_ctx = context + {error={step, type, message, exit_code}}
  execute recovery steps
  if recovery success: return recovered(primary_error)
  else: return failed_with_primary_and_recovery(primary_error, recovery_error)
```

### 13.12 `serialize_argv`

```text
function serialize_argv(argv_items, context):
  out = []
  for item in argv_items:
    if scalar: out += [stringify(render(item))]
    elif option-map:
      (k, v) = single entry
      rv = render(v)
      apply bool/null/empty/list/0/"false" rules
    elif conditional-item:
      if eval(item.when): serialize item.then
    else: fail invalid argv item
  return out
```

---

## 14) Examples

### 14.1 Minimal launcher -> command

```yaml
version: 2

params:
  name:
    type: string
    required: true

commands:
  greet:
    run:
      program: python
      argv:
        - -c
        - "print('hello')"
        - { --name: $params.name }

launchers:
  greet:
    title: Greet
    use: greet
```

### 14.2 Pipeline with nested pipeline

```yaml
version: 2

commands:
  prepare:
    run: { program: python, argv: ["-c", "print('prepare')"] }
  execute:
    run: { program: python, argv: ["-c", "print('execute')"] }

pipelines:
  inner:
    steps:
      - prepare
      - execute

  outer:
    steps:
      - inner

launchers:
  run_outer:
    title: Run outer
    use: outer
```

### 14.3 Foreach over struct_list

```yaml
version: 2

params:
  jobs:
    type: struct_list
    item_schema:
      url: { type: string }

commands:
  fetch_one:
    run:
      program: python
      argv:
        - -c
        - "print('fetch')"
        - { --url: $url }

pipelines:
  batch:
    steps:
      - step: per_job
        foreach:
          in: $params.jobs
          as: job
          steps:
            - use: fetch_one
              with:
                url: $job.url

launchers:
  batch:
    title: Batch
    use: batch
```

### 14.4 Full example (imports + profiles + locals + launchers + on_error)

```yaml
version: 2

imports:
  fs: ./packs/fs.yaml
  media: ./packs/media.yaml

profiles:
  home:
    workdir: "D:\\MediaAutomation"
    env:
      PYTHONUNBUFFERED: "1"
    runtimes:
      python: "D:\\Python312\\python.exe"

params:
  source_url:
    type: string
    required: true
  collection:
    type: string
    default: "incoming"

locals:
  run_root: "${profile.workdir}\\runs\\${run.id}_${params.collection}"
  urls_file: "${locals.run_root}\\urls.json"

pipelines:
  ingest:
    steps:
      - media.scrape_source
      - step: move
        use: fs.move_from_manifest
        with:
          manifest_file: $locals.urls_file
    on_error:
      steps:
        - step: cleanup
          use: fs.remove_file
          with:
            path: $locals.urls_file

launchers:
  ingest:
    title: Ingest
    use: ingest
```

---

## 15) YAML pitfalls and recommendations

1. Strings like `yes/no/on/off` SHOULD be quoted to avoid YAML bool coercion.
2. Windows paths SHOULD be quoted, e.g. `"C:\\tmp\\file.txt"`.
3. Strings containing `:` SHOULD be quoted, e.g. `"Header: Value"`.
4. Inline maps are compact but fragile; multiline map form SHOULD be preferred for complex cases.
5. `$` MUST be escaped as `$$` for literal dollar.
6. YAML anchors/aliases are not forbidden by parser, but are not part of DSL compatibility contract.

---

## 16) Migration notes from v1 to v2-lite

This section is documentation-only and does not mandate automatic migration tooling.

1. Top-level mapping:
   - v1 `actions` -> v2 `launchers`
   - v1 `vars` -> v2 `locals`
   - v1 `runtime` -> v2 `profiles.<name>.runtimes`
   - v1 `app.workdir/env/shell` is replaced by profile-centric and command/run-centric model.
2. UI model:
   - v1 action-centric UI -> v2 launcher-centric UI.
   - root `params` define launcher form model.
   - launcher `with` prebinds read-only values.
3. Callable model:
   - v1 action may own run/pipeline.
   - v2 separates UI entrypoint (`launcher`) and callable (`command`/`pipeline`).
4. argv DSL:
   - v1 accepted string/short-map/extended-option-object.
   - v2 supports scalar/option-map/`{when, then}`.
   - v1 extended-option compatibility is NOT implied.
5. Recovery:
   - v1 concept preserved.
   - v2 formalizes `$error.*`, statuses, and recovery phase.
6. Imports:
   - absent in v1, namespace+acyclic graph in v2.
7. Persistence expectations:
   - v1 action-based presets/state are legacy.
   - v2 should be launcher-based.
   - automatic migration is not guaranteed in draft 1.

Manual migration guidance:

- extract action form fields into root `params`;
- move reusable constants into `locals`;
- split reusable process launches into `commands`;
- compose workflows as `pipelines`;
- expose only UI entrypoints as `launchers`.

---

## 17) Compatibility and migration strategy

1. v1 and v2 MUST coexist by root `version` dispatch.
   - `version: 1` => legacy engine.
   - `version: 2` => v2 engine.
2. No in-place semantic compatibility layer is required.
   - v2 engine MUST NOT execute v1 semantics.
   - v1 engine remains unchanged as legacy.
3. No automatic migration guarantee in draft 1.
4. v1/v2 docs, examples, and tests SHOULD coexist and remain version-specific.
5. Existing v1 behavior MUST NOT be silently reinterpreted as v2.

| Topic | v1 | v2-lite | Compatibility |
| --- | --- | --- | --- |
| top-level entrypoints | `actions` | `launchers` | incompatible, manual migration |
| reusable constants | `vars` | `locals` | conceptually similar, semantics changed |
| imports | not defined | namespace + DAG imports | new in v2 |
| argv DSL | string/short-map/extended-option | scalar/option-map/conditional | not wire-compatible |
| recovery | action-level `on_error` concept | command/pipeline `on_error` formalized | partial conceptual continuity |
| profiles/runtime | top-level `runtime` (+ app env/workdir) | selected `profile` with runtimes/env/workdir | model changed |
| presets/state expectations | action-based legacy | launcher-based target | migration not guaranteed |

---

## 18) Responsibility split between UI and engine

| concern | UI responsibility | engine responsibility | boundary / contract |
| --- | --- | --- | --- |
| root YAML selection | choose/open file | parse/load docs | UI passes path; engine returns model/errors |
| launcher selection | user chooses launcher | resolve launcher target | UI passes launcher id |
| profile selection | user/app selects profile | validate profile exists | UI passes profile id |
| param form | render controls, gather values | validate values authoritative | UI sends collected params |
| secrets flow | unlock vault / collect secret inputs | consume resolved secret values/handles | secret transport format is implementation-defined |
| imports | n/a | resolve/import/validate graph | engine-only concern |
| validation | pre-check UX hints | canonical static/runtime validation | engine is source of truth |
| locals/templates/expressions | n/a | evaluate deterministically | engine-only semantics |
| argv serialization | n/a | deterministic tokenization | engine returns argv-driven process outcome |
| execution | start/stop commands from user intent | execute command/pipeline/foreach/on_error | UI sends cancel request; engine enforces |
| results/logs | display status/history | produce structured results/log events | engine emits structured data for UI |
| presets/history persistence | store/load UI state | MUST NOT require UI widget dependencies | UI layer concern |

Boundary contract:

- UI MUST pass: selected launcher name, selected profile name, validated param values, resolved secret values or secret handles.
- Engine MUST return: structured run result, structured step tree/results, structured logs/events suitable for UI display.
- Engine MUST NOT depend on Tk widgets.
- UI MUST NOT reimplement execution semantics.

---

## 19) Intentionally not supported in draft 1

- `parallel`.
- imported params merge model / `param_imports`.
- rich public foreach per-iteration result addressing.
- pipeline-level locals.
- custom expression functions.
- vault file/storage format.
- static dependency analysis for minimal launcher form.

---

## 20) Acceptance criteria for backlog step 1 (documentation)

The spec document MUST include:

1. clear lifecycle for profile selection, param defaults, run.id creation, locals evaluation;
2. formal short-name resolution order and shadowing rules;
3. validation/runtime phase matrix;
4. detailed error-phase table;
5. migration notes v1->v2;
6. compatibility strategy;
7. UI vs engine responsibility matrix.

