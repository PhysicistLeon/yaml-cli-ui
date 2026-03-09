# Manual migration guide: v1 -> v2-lite

This guide is for teams moving configs from legacy `version: 1` to current `version: 2`.

## Migration model (high level)

- Migration is **manual** (no converter in this repository).
- v1 and v2 are supported **side-by-side** via version routing.
- Migrate YAML config first; do not expect history/storage auto-upgrade.
- Keep legacy v1 workflows runnable while incrementally introducing v2 files.

## v1 -> v2 mapping table

| v1 | v2-lite | Comment |
| --- | --- | --- |
| `actions` | `launchers` | UI entrypoints moved to launcher model. |
| `vars` | `locals` | Ordered root locals instead of legacy vars semantics. |
| action `run/pipeline` | launcher `use` + `commands/pipelines` graph | Reuse moves into callable namespace. |
| path `kind: file/dir` | param types `filepath` / `dirpath` | Stronger explicit type names. |
| legacy argv DSL | scalar / option-map / `{ when, then }` | Smaller argv surface in v2-lite. |
| action-level persistence | launcher-level persistence | Presets/state keyed by launcher. |
| `<yaml>.presets.json` (v1 shape) | v2 presets/state files | Separate v2 JSON files and shape. |
| runtime aliases (`runtime.*`) | `profiles.<name>.runtimes` | Profile-selected runtime mapping. |
| action-oriented UI flow | launcher-oriented UI flow | Dialog and state are launcher-centric. |

## What disappeared / simplified / replaced

| Category | v1 | v2-lite |
| --- | --- | --- |
| Extended argv option object | broad legacy shape | reduced argv forms only |
| Global center | `actions` holds everything | split into launchers + callables |
| Vars semantics | legacy ad-hoc | ordered root `locals` |
| Persistence schema | v1 single shape | dedicated v2 launcher presets + state |

## Before/after examples

### 1) Simplest command

**v1**

```yaml
version: 1
actions:
  ping:
    title: Ping
    pipeline:
      - run:
          program: python
          argv: ["-V"]
```

**v2**

```yaml
version: 2
commands:
  py_version:
    run:
      program: python
      argv: ["-V"]
launchers:
  ping:
    title: Ping
    use: py_version
```

### 2) Command + pipeline

**v1 action pipeline**

```yaml
version: 1
actions:
  build:
    pipeline:
      - run: { program: python, argv: ["prep.py"] }
      - run: { program: python, argv: ["build.py"] }
```

**v2 commands + pipeline + launcher**

```yaml
version: 2
commands:
  prep: { run: { program: python, argv: ["prep.py"] } }
  build: { run: { program: python, argv: ["build.py"] } }
pipelines:
  build_all:
    steps: [prep, build]
launchers:
  build:
    title: Build
    use: build_all
```

### 3) Reuse with imports

**v1 (usually copy/paste between files)**

```yaml
# file A and B each duplicate same run blocks in actions.pipeline
```

**v2 (shared pack via imports)**

```yaml
version: 2
imports:
  common: ./packs/common.yaml
pipelines:
  flow:
    steps: [common.prepare, common.publish]
launchers:
  run:
    title: Run
    use: flow
```

### 4) Batch / foreach

**v1**

```yaml
version: 1
actions:
  batch:
    pipeline:
      - foreach:
          in: "${form.items}"
          as: item
          do:
            - run: { program: echo, argv: ["${item}"] }
```

**v2**

```yaml
version: 2
commands:
  echo_item:
    run:
      program: echo
      argv: ["${$loop.item}"]
pipelines:
  batch:
    steps:
      - foreach:
          in: "${$params.items}"
          as: item
          steps: [echo_item]
launchers:
  batch:
    title: Batch
    use: batch
```

## Manual migration checklist

1. Identify one target v1 action and freeze its expected behavior.
2. Extract reusable process launches into `commands`.
3. Move orchestration into `pipelines`.
4. Replace `vars` with ordered root `locals`.
5. Convert top-level buttons to `launchers`.
6. Rewrite argv entries to v2 forms (scalar/option-map/conditional).
7. Verify explicit namespaces (`$params/$locals/$profile/$steps/$run/$loop/$error`).
8. Re-check secret handling (`secret` params, avoid persistence leaks).
9. Manually create fresh v2 presets/state files only if needed.
10. Run smoke checks for routing/examples/docs.

## Anti-patterns and incompatibilities (practical)

- Using short `$name` when name is ambiguous across params/locals/bindings.
- Referencing a future local from earlier `locals` entry.
- Trying to define pipeline-level locals (not supported in v2-lite).
- Mixing `when` and option-map payload incorrectly (conditional item requires `then`).
- Expecting shell splitting inside one argv string (`shell=False` execution).
- Storing secrets in presets/state JSON files.
- Expecting automatic migration of old v1 storage.
- Trying to import `launchers`/`profiles` as library sections.
- Keeping old mental model "action contains everything" instead of callable graph + launcher.

## What will probably break

- Legacy v1 extended argv tricks not representable in v2-lite argv forms.
- Implicit variable/name resolution that relied on v1-only conventions.
- Any workflow assuming v1 presets JSON shape is reused as-is in v2.
- Workflows relying on unsupported deferred features (`parallel`, `param_imports`).
- Copying v1 action blocks verbatim without introducing `commands`/`pipelines`/`launchers` split.
