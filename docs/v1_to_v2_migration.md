# Migration guide: v1 -> v2-lite

This guide is for manual migration in a side-by-side repository where both versions remain supported.

## 1) Migration strategy (high-level)

- Migration is **manual** (no converter in this repo).
- v1 and v2 are expected to coexist during transition.
- Rewrite config first; keep historical storage/application history as-is.
- Validate v2 behavior with smoke runs before replacing user-facing shortcuts.

## 2) Mapping table: v1 -> v2

| v1 concept | v2-lite concept | Notes |
| --- | --- | --- |
| `actions` | `launchers` | UI entrypoints move to launcher list. |
| `vars` | `locals` | Root ordered locals with explicit namespace usage. |
| action `run`/`pipeline` | launcher `use` -> callable graph | Orchestration moves into `commands`/`pipelines`. |
| `path + kind` fields | param type `filepath` / `dirpath` | Path intent becomes explicit param type. |
| legacy argv option forms | v2 argv scalar / option-map / `{when, then}` | Keep argv declarative and deterministic. |
| action-level persistence | launcher-level persistence | v2 stores per launcher. |
| v1 `<yaml>.presets.json` | v2 `<yaml>.launchers.presets.json` + `<yaml>.state.json` | Separate files by concern. |
| runtime aliases (`runtime`) | `profile.runtimes` | Selected profile resolves executable aliases. |
| action-centric UI | launcher-oriented UI | Launch button => callable target with fixed bindings. |

## 3) Removed / simplified / replaced

| Category | v1 | v2-lite |
| --- | --- | --- |
| argv extended object | multiple legacy object variants | compact scalar/map/conditional model |
| central orchestrator unit | action as “all-in-one” | split into launchers + callable namespace |
| vars behavior | legacy implicit patterns | explicit ordered `locals` + namespaces |
| persistence shape | single presets file | dedicated presets + state files |

## 4) Before/after examples

> Notes: these migration snippets are intentionally simplified and should be adapted to your real workflow (paths, profiles, secrets, and environment details).

### 4.1 Minimal command

**v1**

```yaml
version: 1
actions:
  hello:
    title: Hello
    pipeline:
      - id: run
        run:
          program: python
          argv: [-c, "print('hello')"]
```

**v2-lite**

```yaml
version: 2
commands:
  hello_cmd:
    run:
      program: python
      argv: [-c, "print('hello')"]
launchers:
  hello:
    title: Hello
    use: hello_cmd
```

### 4.2 Command + pipeline

**v1**

```yaml
version: 1
actions:
  build:
    pipeline:
      - id: prep
        run: { program: python, argv: [-c, "print('prep')"] }
      - id: run
        run: { program: python, argv: [-c, "print('build')"] }
```

**v2-lite**

```yaml
version: 2
commands:
  prep: { run: { program: python, argv: [-c, "print('prep')"] } }
  run_build: { run: { program: python, argv: [-c, "print('build')"] } }
pipelines:
  build_flow:
    steps: [prep, run_build]
launchers:
  build:
    title: Build
    use: build_flow
```

### 4.3 Reuse via imports

**v1 pattern (copy/paste call blocks)**

```yaml
version: 1
actions:
  ingest:
    pipeline:
      - id: scrape_a
        run: { program: python, argv: [scripts/scrape.py, a] }
      - id: scrape_b
        run: { program: python, argv: [scripts/scrape.py, b] }
```

**v2-lite (imported reusable callables/locals)**

```yaml
version: 2
imports:
  media: ./packs/media.yaml
launchers:
  ingest:
    title: Ingest
    use: media.scrape_all
```

### 4.4 Batch / foreach

**v1**

```yaml
version: 1
vars:
  items:
    - alpha
    - beta
actions:
  batch:
    title: Batch
    pipeline:
      - id: each
        foreach:
          in: "${vars.items}"
          as: item
          pipeline:
            - id: run
              run:
                program: python
                argv: [-c, "import sys; print(sys.argv[1])", "${item}"]
```

**v2-lite**

```yaml
version: 2
params:
  items:
    type: struct_list
commands:
  run_item:
    run:
      program: python
      argv: [-c, "import sys; print(sys.argv[1])", $item.name]
pipelines:
  batch:
    steps:
      - foreach:
          in: $params.items
          as: item
          steps: [run_item]
launchers:
  batch:
    title: Batch
    use: batch
```

## 5) Manual migration checklist

1. Identify current v1 action(s) and intended launcher UI points.
2. Extract reusable process launches into `commands`.
3. Extract orchestration into `pipelines`.
4. Replace `vars` with ordered root `locals`.
5. Move top-level buttons to `launchers` (`title`, `use`, optional `with`).
6. Replace argv syntax with scalar / option-map / `{when, then}`.
7. Recheck all variable references and migrate to explicit namespaces.
8. Revalidate secret handling (`type: secret`, source, persistence exclusions).
9. Create new v2 presets/state files manually only if needed.
10. Run smoke checks on routing, loading, and launcher execution.

Migration pseudo-grammar:

```text
V1ToV2Migration :=
  read old v1 config
  identify actions/vars/argv patterns
  map to launchers/locals/commands/pipelines
  verify params and secrets
  verify imports/profiles
  rewrite persistence expectations
  run smoke checks
```

## 6) What will probably break

- Unqualified `$name` references where scope is ambiguous.
- Locals referencing future locals (ordering now validated).
- Trying to define pipeline-level locals.
- Mixing `when` and option-map semantics without a `then` wrapper.
- Expecting shell-style splitting from one argv string.
- Persisting secrets in presets/state.
- Expecting automatic migration of legacy v1 storage.
- Importing `launchers` or `profiles` from library packs.
- Keeping old mental model “action = full orchestration + UI + state”.

## 7) Anti-patterns checklist

Avoid these anti-patterns in migrated configs:

- Use explicit namespaces (`$params.foo`, not bare `$foo`) when names can collide.
- Do not reference not-yet-declared locals.
- Do not place ad-hoc locals inside pipeline blocks.
- In argv conditions, always use `{ when: ..., then: ... }` shape.
- Do not rely on shell tokenization; provide one argv item per token.
- Never store secret values in presets/state files.
- Do not assume legacy files are auto-converted.
- Do not use imports as if they can merge launcher/profile sections.
