# v2-lite examples cookbook

This page is intentionally short and practical. Copy small parts into your own config.

## 1) Minimal v2 config

```yaml
version: 2
commands:
  hello:
    run:
      program: python
      argv: [-c, "print('hello')"]
launchers:
  hello:
    title: Hello
    use: hello
```

Use this as the smallest valid launcher-driven setup. Good for smoke checks and onboarding.

## 2) Imports example

```yaml
version: 2
imports:
  media: ./packs/media.yaml
launchers:
  scrape:
    title: Scrape
    use: media.scrape
```

Imports let you reuse command/pipeline/local packs without copy/paste. Keep launchers in root document.

## 3) Profile example

```yaml
profiles:
  local:
    workdir: .
    runtimes:
      python: python
```

Profiles group environment defaults. Runtime aliases decouple DSL `program` from machine-specific executable paths.

## 4) Locals example

```yaml
params:
  collection: { type: string, default: inbox }
locals:
  out_dir: "${profile.workdir}/out/${params.collection}"
```

Locals centralize derived values. Declare in dependency order; future-local references fail validation.

## 5) argv example

```yaml
argv:
  - scripts/run.py
  - { --input: $params.input }
  - { when: $params.verbose, then: --verbose }
```

Use scalar tokens, option maps, and explicit conditionals. Each argv list item maps to one subprocess argument/token.

## 6) Nested pipeline example

```yaml
pipelines:
  ingest:
    steps:
      - prep
      - process
      - publish
```

Pipelines are orchestration units. They keep command-level process specs small and reusable.

## 7) Foreach example

```yaml
steps:
  - foreach:
      in: $params.jobs
      as: job
      steps:
        - use: process_one
          with: { item_name: $job.name }
```

Foreach is good for batch processing lists. Use `with` to bind per-item values explicitly.

## 8) on_error example

```yaml
commands:
  risky:
    run: { program: python, argv: [scripts/risky.py] }
    on_error:
      steps:
        - notify_failure
```

`on_error` captures recovery/cleanup workflow close to the failing callable, making failures easier to reason about.

## 9) Launcher with fixed bindings

```yaml
launchers:
  quick_ingest:
    title: Ingest inbox
    use: ingest
    with:
      collection: inbox
```

`with` values are fixed/read-only in launcher dialog and not persisted as editable last values.

## See also

- `examples/v2_minimal.yaml`
- `examples/v2_ingest_demo.yaml`
- `docs/v2_spec.md`
- `docs/v1_to_v2_migration.md`
