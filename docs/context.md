# CLI YAML Pipeline Engine — Context for Codex

## 1. Goal / Definition of Done

Build a **Python application** that:

* Loads a YAML file describing a CLI-driven workflow.
* Shows top-level actions as a set of quick-launch buttons.
* Opens a modal parameter dialog for the selected action and collects user inputs.
* Executes a **pipeline of CLI steps**.
* Safely constructs subprocess calls using an **argv list (NOT shell strings)**.
* Supports batch operations, conditional steps, and reusable variables.

### Definition of Done

The project is complete when:

1. A YAML file alone can define:

   * UI fields
   * CLI arguments
   * execution pipeline
2. The program can:

   * render top-level action buttons
   * open per-action parameter forms in modal dialogs
   * validate inputs
   * assemble argv deterministically
   * run independent actions in parallel
3. Switching YAML files immediately changes the interface and behavior.
4. No code changes are required to add new commands/workflows.
5. Works reliably on Windows.

---

## 2. Constraints

### Windows-first

The system MUST:

* Use subprocess with `shell=False` by default.
* Support Windows paths (`C:\...`).
* Provide helpers for:

  * creating directories (PowerShell allowed)
  * opening folders (`explorer.exe`)
* Resolve environment variables from Windows.

---

### Fast YAML switching

Design goal:

* YAML is the **single source of truth**
* UI is generated dynamically
* No compiled schema

The engine MUST:

* Reload YAML without restart (or support quick restart)
* Validate YAML structure before execution
* Fail loudly on invalid expressions

---

## 3. YAML Schema + Full Engine Specification

---

# 3.1 Top-level structure

```yaml
version: 1
app: {...}
runtime: {...}
vars: {...}
actions: {...}
```

Implementation constraints (v1):

* only `version: 1` is supported
* `actions` is required and must be a non-empty map

---

# 3.2 app section

Optional.

Fields:

* title: string
* platform: windows|linux|mac|any
* shell: bool (default false)
* workdir: string
* env: map<string,string>

`shell=false` MUST be default.

---

# 3.3 vars section

Dictionary of named values.

Supports either:

### simple form

```yaml
vars:
  download_dir: "C:\\Downloads"
```

### extended form (same types as form fields)

```yaml
vars:
  download_dir:
    type: path
    default: "${home}\\Downloads"
```

Variables accessible as:

```
${vars.download_dir}
```

---

# 3.4 actions

Dictionary:

```
actions:
  action_id: ActionDef
```

ActionDef:

* title: string (required)
* info: string (optional, UI tooltip text for action button)
* form: optional
* pipeline: optional list of steps
* run: optional run step shortcut

Action must define at least one of: `pipeline` or `run`.

Shortcut:

```
run: {...}
```

treated as one-step pipeline.

---

# 3.4.1 runtime section

Optional.

Supported fields:

* `python.executable`: string path to Python interpreter

When a run step has `program: "python"`, engine may override it with
`runtime.python.executable`.

---

# 3.5 Supported form field types (v1)

Each field:

```
id: string
type: string
label: optional
default: optional
required: bool
```

---

### Primitive types

string
text (multiline)

path

* kind: file|dir
* must_exist: bool
* multiple: bool

bool

tri_bool
values MUST be:

```
"auto" | "true" | "false"
```

choice

* options: [...]

multichoice

* options: [...]

int
float

Numeric fields MAY render as sliders when `min` and `max` are present. YAML can provide optional UI hints via `widget: "slider" | "input" | "spinbox"`; unknown keys remain engine-safe (ignored by executor) while UI may use them. If `widget` is omitted, UI chooses the control automatically.

For `float` slider UIs, use integer-backed scaling to avoid precision artifacts: choose `scale = 10^decimals` (for example `step: 0.05` → `scale=100`), keep slider state as integer, and expose value as `int_value/scale`.

secret

* source: inline|env
* env: NAME

---

### Structured types

kv_list

Represents:

```
[{k:"Header", v:"Value"}]
```

struct_list

```
list<object>
```

Requires:

```
item_schema: {...}
```

---

# 3.6 Templates

Strings may contain:

```
${expression}
```

If expression returns null → empty string.

---

# 3.7 Expression language

Must support:

* literals
* vars.x
* form.x
* env.NAME
* cwd home temp os
* step.<id>.stdout
* comparisons == != < > <= >=
* boolean and/or/not
* parentheses

Supported helpers (allowlist):

* len(x)
* empty(x)
* exists(path)

Must NOT allow arbitrary code execution.
Calls to any other functions are not allowed.

---

# 3.8 Pipeline Steps

Each step:

```
id: string
when: optional expression
continue_on_error: bool
```

Step type must be one of:

* run
* pipeline
* foreach

---

## run step

```
run:
  program: string
  argv: [...]
  workdir: optional
  env: optional
  shell: optional
  timeout_ms: optional
  capture: bool
  stdout: inherit|capture|file:<path>
  stderr: same
```

Must run with argv list.

---

## pipeline step

Nested sequential steps.

---

## foreach step

```
foreach:
  in: expression returning list
  as: variable name
  steps: [...]
```

Expose:

```
${job.field}
${loop.index}
```

---

# 3.9 ARGUMENT SERIALIZATION (CRITICAL)

argv is a list of ArgItem.

ArgItem may be:

1. string
2. short map
3. extended option object

---

## 1) String ArgItem

After template expansion:

Add as **single argv element**.
Never split by spaces.

---

## 2) Short map form

Example:

```
- "--cookies": "${form.cookies}"
```

Rules:

value = evaluated result

| value      | result              |
| ---------- | ------------------- |
| true       | add `[opt]`         |
| false/null | omit                |
| ""         | omit                |
| string     | `[opt,value]`       |
| number     | `[opt,str(value)]`  |
| list       | repeat `[opt,item]` |

---

## 3) Extended option object

```
- opt: "--sub-langs"
  from: "${form.sub_langs}"
  mode: join
  joiner: ","
  style: separate
  omit_if_empty: true
  when: "${form.enabled}"
  template: "{k}:{v}"
  false_opt: "--no-write-subs"
```

Fields:

* opt (required)
* from
* when optional
* omit_if_empty default true
* mode:

  * auto
  * flag
  * value
  * repeat
  * join
* joiner default ","
* style:

  * separate → `--opt value`
  * equals → `--opt=value`
* template optional
* false_opt optional

---

## empty definition

True if:

* null
* empty string
* empty list

---

## mode=auto resolution

bool → flag
list → repeat
other → value

---

## tri_bool logic

value:

auto → omit
true → add opt
false → add false_opt if provided, else omit

---

## repeat mode

Each item:

* if template exists → render template
* add per style

---

## join mode

Join items with joiner → one argument.

---

# 3.10 Step results

Engine MUST store:

```
step.<id>.exit_code
step.<id>.stdout
step.<id>.stderr
step.<id>.duration_ms
```

If step has no explicit `id`, engine generates `step_<n>`.

---

# 3.11 Error handling

Default:

Non-zero exit → stop pipeline.

If:

```
continue_on_error: true
```

pipeline continues.

Invalid expression MUST be fatal.

---

# 3.12 Implementation caveats (as-implemented)

* `vars` resolution is single-pass (no recursive stabilization).
* `vars` resolution depends on map iteration order.
* Template rendering is applied to string values only; non-string values are returned as-is.
* `foreach.in` must resolve to list (other iterables are rejected).
* `program: python` override is applied only for exact `"python"` match.

---

## 4. Reference Example YAML

```yaml
version: 1

vars:
  download_dir:
    type: path
    kind: dir
    default: "${home}\\Downloads\\yt"

actions:

  yt_audio:

    title: "Download audio"

    form:
      fields:

        - id: url
          type: string
          required: true

        - id: bitrate
          type: choice
          options: ["128K","192K","320K"]
          default: "192K"

        - id: embed
          type: bool
          default: true

    pipeline:

      - id: ensure_dir
        run:
          program: "powershell"
          argv:
            - "-NoProfile"
            - "-Command"
            - "New-Item -ItemType Directory -Force -Path '${vars.download_dir}' | Out-Null"

      - id: download
        run:
          program: "yt-dlp"
          argv:
            - "--extract-audio": true
            - "--audio-format": "mp3"
            - "--audio-quality": "${form.bitrate}"
            - "--embed-thumbnail": "${form.embed}"
            - "-o": "${vars.download_dir}\\%(title)s.%(ext)s"
            - "${form.url}"
```

---

## 5. Notes / Edge Cases

### MUST NOT split argv strings

```
"-o C:\file name"
```

is one argument.

---

### Always treat YAML order as authoritative

Never reorder options.

---

### Path quoting

Do NOT manually quote paths when shell=false.
Let subprocess pass raw strings.

---

### tri_bool exists for real CLI behavior

Without tri_bool, user cannot represent:

* leave default
* force enable
* force disable

---

### kv_list typical mapping

```
- opt: "--header"
  from: "${form.headers}"
  mode: repeat
  template: "{k}: {v}"
```

---

### struct_list enables batch pipelines

Example:

```
foreach:
  in: "${form.jobs}"
  as: job
```

---

### Windows-specific reality

Prefer:

* PowerShell for filesystem tasks
* explorer.exe for opening directories

Avoid:

* cmd redirection when possible

---

END OF CONTEXT


## 4. UX behavior (current app)

- Main window lists top-level `actions` as buttons (no action dropdown).
- Clicking a button opens the parameter dialog only when editable fields exist; otherwise the action starts immediately.
- Validation errors prevent launch and do not change action status color.
- Action status colors: idle = neutral, running = yellow, success = green, failed = red.
- Output uses tabs: aggregate `All runs` + one tab per action.
- Each action tab includes run history selector so previous outputs remain available.
