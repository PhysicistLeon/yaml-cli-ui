# v2-lite examples cookbook

This page is intentionally short and practical. Snippets below are either full valid YAML docs or explicitly marked as partial blocks.

## 1) Minimal v2 config (full, valid)

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

Use this as the smallest valid launcher-driven setup for smoke checks and onboarding.

## 2) Imports example (full, valid)

```yaml
version: 2
imports:
  media: ./packs/media.yaml
launchers:
  scrape:
    title: Scrape jobs
    use: media.scrape_all
```

Imports let you reuse command/pipeline/local packs without copy/paste. Keep `launchers` in the root document.

## 3) Profile example (partial block)

```yaml
profiles:
  local:
    workdir: .
    runtimes:
      python: python
```

This is a valid `profiles` section to paste into a full v2 document. Runtime aliases map DSL program names to concrete executables.

## 4) Locals example (partial block)

```yaml
params:
  collection: { type: string, default: inbox }
locals:
  out_dir: "${profile.workdir}/out/${params.collection}"
```

Locals centralize derived values. Declare in dependency order; references to future locals fail validation.

## 5) argv example (partial `run.argv` block)

```yaml
argv:
  - scripts/run.py
  - { --input: $params.input }
  - { when: $params.verbose, then: --verbose }
```

Use scalar tokens, option maps, and explicit conditionals. One YAML list item becomes one subprocess argv token.

## 6) Nested pipeline example (full, valid)

```yaml
version: 2
commands:
  prep:
    run: { program: python, argv: [-c, "print('prep')"] }
  process:
    run: { program: python, argv: [-c, "print('process')"] }
  publish:
    run: { program: python, argv: [-c, "print('publish')"] }
pipelines:
  ingest:
    steps: [prep, process, publish]
launchers:
  ingest:
    title: Ingest
    use: ingest
```

Pipelines are orchestration units. Keep process details in commands and sequence logic in pipelines.

## 7) Foreach example (full, valid)

```yaml
version: 2
params:
  jobs:
    type: struct_list
    default:
      - { name: alpha }
commands:
  process_one:
    run:
      program: python
      argv: [-c, "import sys; print(sys.argv[1])", $job.name]
pipelines:
  batch:
    steps:
      - foreach:
          in: $params.jobs
          as: job
          steps:
            - process_one
launchers:
  batch:
    title: Batch
    use: batch
```

Foreach is good for batch processing lists. The `as` name (`job`) becomes available to nested steps.

## 8) on_error example (full, valid)

```yaml
version: 2
commands:
  risky:
    run: { program: python, argv: [-c, "import sys; sys.exit(1)"] }
  notify_failure:
    run: { program: python, argv: [-c, "print('recover')"] }
pipelines:
  run_with_recovery:
    steps: [risky]
    on_error:
      steps: [notify_failure]
launchers:
  risky:
    title: Run risky
    use: run_with_recovery
```

`on_error` keeps cleanup/recovery explicit and produces recovered status when recovery succeeds.

## 9) Launcher with fixed bindings (partial block)

```yaml
launchers:
  quick_ingest:
    title: Ingest inbox
    use: ingest
    with:
      collection: inbox
```

`with` values are fixed/read-only in launcher dialog and are not persisted as editable last values.

## 10) When to prefer explicit namespaces

Prefer explicit names when collisions are possible:

- Use `$params.collection` instead of `$collection` when a local with same name can exist.
- Use `$locals.out_dir` instead of `$out_dir` when a step `with` binding may shadow it.
- Use `$profile.workdir` instead of `$workdir` when launcher/step binds a similarly named value.

## See also

- `examples/v2_minimal.yaml`
- `examples/v2_ingest_demo.yaml`
- `examples/packs/media.yaml`
- `examples/packs/fs.yaml`
- `docs/v2_spec.md`
- `docs/v1_to_v2_migration.md`
