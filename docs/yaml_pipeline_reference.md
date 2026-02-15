# YAML Pipeline Reference (v1, as implemented)

This document is a **self-contained** reference for writing YAML workflows for the CLI YAML Pipeline Engine (Python). It is written to be usable **without reading the source code**.

---

## 1. Overview

The CLI YAML Pipeline Engine:

* Loads a YAML file describing a CLI-driven workflow.
* Shows top-level actions as a set of **quick-launch buttons**.
* Opens a modal parameter dialog for the selected action and collects user inputs.
* Executes a **pipeline of CLI steps**.
* Safely constructs subprocess calls using an **argv list** (not shell strings).
* Supports **conditional steps**, **nested pipelines**, and **batch execution** via `foreach`.
* Provides a small **DSL** for building CLI arguments (`argv`) from values.

---

## 2. Hard rules (as implemented)

1. Only `version: 1` is supported.
2. `actions` is **required** and MUST be a non-empty map.
3. Each action MUST have `title` and at least one of: `pipeline` or `run`.
4. If an action has only `run`, the engine wraps it into a one-step `pipeline`.
5. Supported step types are limited to: `run`, `pipeline`, `foreach`.
6. Template rendering (`${...}`) applies **only to strings**, and only in specific places (see §6).
7. Expression evaluation is sandboxed by an AST allowlist; only these calls are allowed: `len`, `empty`, `exists`.
8. The alias `program: python` can be overridden via `runtime.python.executable`.

---

## 3. Minimal YAML structure

```yaml
version: 1

app:
  shell: false
  workdir: "C:\\work"
  env:
    PYTHONUNBUFFERED: "1"

runtime:
  python:
    executable: "C:\\venv\\Scripts\\python.exe"

vars:
  repo: "C:\\work\\project"

actions:
  do_job:
    title: "Run job"
    pipeline:
      - id: step1
        run:
          program: python
          argv:
            - "script.py"
```

---

## 4. Conventions used in this doc

* **MUST / SHOULD / MAY** are used in the RFC sense.
* Windows paths inside **double-quoted YAML strings** require escaping backslashes: `\\`.
* YAML block scalars:

  * `|` preserves newlines
  * `>` folds newlines into spaces (often nicer for PowerShell `-Command`)

---

## 5. Top-level keys

### 5.1 `version` (required)

* MUST be `1`.

### 5.2 `app` (optional)

Global execution defaults.

```yaml
app:
  shell: false
  workdir: "C:\\repo"
  env:
    KEY: "value"
```

Fields:

* `shell: bool`
  Default fallback is `false` unless overridden by step/run values.
* `workdir: string`
  Default working directory (used if `run.workdir` is not set).
* `env: map<string,string>`
  Environment key/values applied to all runs (merged; see §9.3).

### 5.3 `runtime` (optional)

Runtime overrides, currently used for Python.

```yaml
runtime:
  python:
    executable: "C:\\venv\\Scripts\\python.exe"
```

Rule (as implemented):

* If a `run.program` resolves to the exact string `"python"` (case-sensitive), it MAY be replaced by `runtime.python.executable`.

**Important:**
`python.exe`, `C:\...\python.exe`, `py`, etc. are **not** aliases. Only the literal `python` is.

### 5.4 `vars` (optional)

Reusable variables for templates and expressions.

```yaml
vars:
  repo: "C:\\work\\project"
  list_file: "${vars.repo}\\list.txt"
```

How values are computed is critical; see §7.

### 5.5 `actions` (required)

Map of action definitions.

```yaml
actions:
  action_id:
    title: "..."
    form: ...
    pipeline: ...
```

---

## 6. Template engine `${...}`: actual semantics

### 6.1 Where templates are rendered

`render_template(...)` is applied only where the engine explicitly calls it:

* values in `vars` (during base-context construction)
* step-level `when` expressions
* `run.program`, `run.workdir`, `run.env.*`
* items in `run.argv` (including short-map and extended-option forms)
* `runtime.python.executable` **when** `program == "python"`

**Notably:** form defaults are not guaranteed to be template-rendered. Treat form defaults as literals unless your UI layer explicitly renders them.

### 6.2 “Full match” vs “string interpolation”

* If the entire string is exactly `${expr}` → returns the **native type** of the expression result (bool/list/number/string/etc.).
* If `${expr}` appears inside a larger string → inserts `str(result)` into the string.
* If `result is None` → inserts `""` (empty string).

Examples:

```yaml
# Returns a list (typed) if vars.items is list
in: "${vars.items}"

# Returns a string
argv:
  - "items=${vars.items}"
```

### 6.3 Expression context

Expressions can access:

* `vars`
* `form`
* `env`
* `step`
* `cwd`, `home`, `temp`, `os`
* functions: `len(x)`, `empty(x)`, `exists(path)`

Access patterns:

* dot: `vars.repo`, `form.url`
* index: `form["url"]` (via DotDict-like behavior)

### 6.4 Expression language restrictions

Expressions are evaluated with an AST allowlist. Only a controlled subset of nodes is allowed (names, constants, attributes, boolean ops, comparisons, subscripts, list/tuple/dict literals, etc.).

Function calls are allowed **only** for:

* `len(...)`
* `empty(...)`
* `exists(...)`

Any other call MUST fail.

---

## 7. `vars`: resolution order and the single-pass limitation

`vars` are computed in two phases:

1. Collect initial values:

   * if a var is a map with `default`, use `default`
   * else use the var value as-is
2. Run **one pass** of `render_template` on each var.

### 7.1 Single pass (no recursive stabilization)

There is **no iterative re-rendering until stable**. This implies:

* dependencies between vars are order-sensitive
* nested references may remain unresolved `${...}` literals

**Anti-pattern:**

```yaml
vars:
  a: "C:\\x"
  b: "${vars.a}\\y"
  c: "${vars.b}\\z"   # may remain partially unresolved
```

**Recommended pattern: build final paths directly from a “root” var:**

```yaml
vars:
  repo: "C:\\x"
  c: "${vars.repo}\\y\\z"
```

---

## 8. Actions and forms

### 8.1 Action definition

Each action MUST have:

* `title: string`
* and at least one of:

  * `pipeline: list`
  * `run: object` (auto-wrapped into a one-step pipeline)

Optional:

* `form` (to collect user parameters)

### 8.2 `form` schema (required for “no-source” usage)

This section defines the **supported field model**. If your current UI differs, align it to this schema for consistency.

```yaml
form:
  fields:
    - id: url
      type: string
      label: "URL"
      required: true
      default: ""
```

#### 8.2.1 Field common properties

All fields support:

* `id: string` (required, unique within the form)
* `type: string` (required)
* `label: string` (optional)
* `default: any` (optional)
* `required: bool` (optional, default `false`)

Validation properties (type-dependent):

* `regex: string` (string/text)
* `min`, `max`, `step` (int/float)

#### 8.2.2 Supported field types (v1)

**Primitive**

* `string`
* `float`
* `int`
* `bool`
* `choice`

  * `options: [ ... ]` (required)
* `multichoice`

  * `options: [ ... ]` (required)
* `path`

  * `kind: file|dir` (optional)
  * `must_exist: bool` (optional, default false)
  * `multiple: bool` (optional, default false)

**Structured**

* `kv_list`
  Value is `list<{k:string, v:string}>` (editable as a table UI).
* `struct_list`
  Value is `list<object>`, with:

  * `item_schema: map<string, FieldDef>` (required)
* `tri_bool`
  Value is the string `"auto" | "true" | "false"`.

**Notes**

* `choice` yields a single string.
* `multichoice` yields `list<string>`.
* `path.multiple: true` yields `list<string>`.

---

## 9. Pipeline steps

A pipeline is a list of steps. The engine executes steps **sequentially**, unless skipped by `when`.

### 9.1 Common step fields

* `id` (optional): if absent, engine generates `step_<n>`
* `when` (optional): expression; if false, step is skipped
* `continue_on_error` (optional bool): if true, error is logged and pipeline continues

### 9.2 Step types

Only these are supported:

* `run`
* `pipeline` (nested)
* `foreach`

---

## 9.3 `run` step

```yaml
- id: run_ps
  run:
    program: "powershell"
    workdir: "${vars.repo}"
    shell: false
    timeout_ms: 30000
    env:
      FOO: "bar"
    argv:
      - "-NoProfile"
      - "-Command"
      - "Write-Host hello"
    stdout: "capture"
    stderr: "capture"
```

#### 9.3.1 Defaults (as implemented)

* `shell`: `run.shell` or fallback to `app.shell` else `false`
* `workdir`: `run.workdir` or fallback to `app.workdir` (else engine default / current)
* `stdout/stderr`:

  * if `capture` is missing or `true` → default is `capture`
  * if `capture: false` → default is `inherit`

#### 9.3.2 Environment merge rules (recommended to document explicitly)

To avoid ambiguity, document this merge order:

1. Base environment = OS process environment (`os.environ`)
2. Merge `app.env` (overrides base)
3. Merge `run.env` (overrides both)

If your current implementation differs, update this section to match.

#### 9.3.3 stdout/stderr routing

Supported values:

* `inherit` — stream directly to parent console
* `capture` — capture in memory and expose via `step.<id>.stdout` / `.stderr`
* `file:<path>` — write captured output to a file

**File output behavior (recommended to specify):**

* Output is written as text.
* The file is overwritten (not appended).
* Parent directories are NOT created automatically; ensure they exist.

---

## 9.4 `pipeline` (nested)

```yaml
- id: phase_a
  pipeline:
    - id: a1
      run: ...
    - id: a2
      run: ...
```

Nested steps run sequentially within the same context (access to `vars`, `form`, and previously produced `step` outputs).

---

## 9.5 `foreach`

```yaml
- id: per_item
  foreach:
    in: "${vars.items}"
    as: item
    steps:
      - id: do_one
        run:
          program: "python"
          argv:
            - "worker.py"
            - "--name"
            - "${item.name}"
```

Requirements:

* `foreach.in` MUST evaluate (typed) to a **list**.
  This typically requires the string to be exactly `${...}` (see §6.2).
* `as` defines the per-iteration variable name (default may be `item` if omitted).
* Each iteration exposes:

  * the `as` variable (`item` above)
  * `loop.index` (0-based integer)

---

## 10. `argv` serialization (DSL)

`run.argv` is a list of argv items. Each argv item is one of:

1. **String**
2. **Short-map** (single-key dict)
3. **Extended option object** (`opt` form)

### 10.1 String

```yaml
argv:
  - "literal"
  - "${vars.path}"
```

Each list element becomes a **single argv token**. No splitting on spaces occurs.

**Anti-pattern:**

```yaml
argv:
  - "python script.py --x 1"  # ONE token, not four
```

### 10.2 Short-map (single-key dict)

```yaml
argv:
  - "script.py"
  - "--name": "${vars.user}"
  - "--verbose": "${form.verbose}"
```

Rules:

* `true` → add only the option (`--flag`)
* `false` / `None` / `""` → omit entirely
* list → repeat `opt value` for each element
* otherwise → `opt value`

**Important:** `"false"` (string) is not `false` (bool).
`"--flag": "false"` yields `--flag false`, not omission.

### 10.3 Extended option (`opt` form)

```yaml
argv:
  - opt: "--langs"
    from: "${vars.langs}"
    mode: join
    joiner: ","
```

Supported fields:

* `opt` (required)
* `from` (optional but typical)
* `when` (optional)
* `mode`: `auto|flag|value|repeat|join`
* `style`: `separate|equals`
* `omit_if_empty` (default `true`)
* `template` (optional)
* `false_opt` (optional)
* `joiner` (for `join`)

#### 10.3.1 Mode behavior

* `auto`:

  * bool → `flag`
  * list → `repeat`
  * otherwise → `value`
* `flag`:

  * `true` → add `opt`
  * `false` + `false_opt` → add `false_opt`
* `value` → one `opt value`
* `repeat` → `opt value` for each element
* `join` → one `opt` + joined string (`joiner`)

#### 10.3.2 Tri-state string shortcut in extended options

If the rendered value is a string in `{"auto","true","false"}`:

* `"auto"` → omit the option
* `"true"` → add `opt`
* `"false"` → add `false_opt` (if provided)

This applies even without `mode: flag`.

#### 10.3.3 `style`

* `separate` (default): `--opt value`
* `equals`: `--opt=value`

Only use `equals` if the target CLI accepts it.

---

## 11. Windows practice (PowerShell + paths)

### 11.1 Recommended PowerShell step pattern

```yaml
run:
  program: "powershell"
  argv:
    - "-NoProfile"
    - "-Command"
    - >
      $src='${vars.src}';
      $dst='${vars.dst}';
      Copy-Item -LiteralPath $src -Destination $dst -Force
```

### 11.2 Paths

* In double-quoted YAML strings: use `\\`
* In block strings (`|` / `>`): backslashes are more readable
* For opening a folder: pass the path as a dedicated argv element

```yaml
run:
  program: "explorer.exe"
  argv:
    - "${vars.target_dir}"
```

---

## 12. Anti-patterns

1. **Deep var dependency chains** (single-pass vars rendering)

2. **Putting full command in one argv string** with `shell: false`

3. **Short-map with ambiguous types**

```yaml
- "--flag": "false"  # string ≠ bool
```

4. **Expecting recursive `${...}` resolution** inside already rendered vars

5. **Using `style: equals` with CLIs that do not support it**

---

## 13. Known limitations

1. No recursive/multi-pass var resolution.
2. Var resolution order depends on map iteration order.
3. `foreach.in` MUST produce a list (other iterables rejected).
4. Expression calls restricted to `len/empty/exists`.
5. Template rendering is applied only in explicit engine-controlled locations.
6. `program: python` override triggers only on the exact string `python`.

---

## 14. Ready-to-use templates

### 14.1 Python runtime override

```yaml
version: 1
runtime:
  python:
    executable: "C:\\code\\Python\\.venvs\\stable\\Scripts\\python.exe"

actions:
  run_script:
    title: "Run script"
    pipeline:
      - id: run
        run:
          program: "python"
          workdir: "C:\\repo"
          argv:
            - "task.py"
            - "--input"
            - "C:\\repo\\input.txt"
```

### 14.2 PowerShell copy artifact

```yaml
version: 1
vars:
  repo: "C:\\_SYNC\\Code\\Python\\WebScraping\\ecom"
  src_xlsx: "${vars.repo}\\result.xlsx"
  dst_xlsx: "${vars.repo}\\video_table_webview\\result.xlsx"

actions:
  copy_result:
    title: "Copy result.xlsx"
    pipeline:
      - id: copy
        run:
          program: "powershell"
          workdir: "${vars.repo}"
          argv:
            - "-NoProfile"
            - "-Command"
            - >
              $src='${vars.src_xlsx}';
              $dst='${vars.dst_xlsx}';
              if (-not (Test-Path -LiteralPath $src)) { throw "Source not found: $src" }
              Copy-Item -LiteralPath $src -Destination $dst -Force
```

### 14.3 Conditional + foreach

```yaml
version: 1
vars:
  names:
    - { name: "alpha" }
    - { name: "beta" }

actions:
  batch:
    title: "Batch run"
    pipeline:
      - id: loop
        foreach:
          in: "${vars.names}"
          as: item
          steps:
            - id: per_item
              when: "${item.name != ''}"
              run:
                program: "python"
                argv:
                  - "worker.py"
                  - "--name": "${item.name}"
```
---