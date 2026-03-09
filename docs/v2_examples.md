# v2-lite examples guide

Short practical snippets for authors writing `version: 2` configs.

## 1) Minimal v2 config

```yaml
version: 2
commands:
  hello:
    run:
      program: python
      argv: ["-c", "print('hello')"]
launchers:
  hello:
    title: Hello
    use: hello
```

Use this as the smallest working baseline: one command + one launcher.

## 2) Imports example

```yaml
version: 2
imports:
  media: ./packs/media.yaml
pipelines:
  main:
    steps: [media.download]
launchers:
  run:
    title: Run
    use: main
```

Imports let you build shared callable libraries without copy-pasting blocks.

## 3) Profile example

```yaml
version: 2
profiles:
  local:
    runtimes:
      python: python
  py312:
    runtimes:
      python: C:\\Python312\\python.exe
```

Profiles are useful when the same workflow runs in different environments.

## 4) Locals example

```yaml
version: 2
locals:
  out_dir: "${$profile.workdir}/out"
  report_path: "${$locals.out_dir}/report.json"
```

Locals centralize reusable derived values and keep command blocks cleaner.

## 5) Argv example

```yaml
argv:
  - "--url"
  - "${$params.url}"
  - {"--verbose": "${$params.verbose}"}
  - when: "${$params.save_json}"
    then: {"--json": true}
```

You can mix literals, option-maps, and conditional argv items in one list.

## 6) Nested pipeline example

```yaml
pipelines:
  prepare_and_run:
    steps: [prepare, run_main]
  full:
    steps: [prepare_and_run, upload]
```

Nested pipelines help split long orchestration into readable reusable units.

## 7) Foreach example

```yaml
pipelines:
  batch:
    steps:
      - foreach:
          in: "${$params.urls}"
          as: item
          steps: [download_one]
```

`foreach` is the v2-lite way to run repeated operations over list input.

## 8) on_error example

```yaml
pipelines:
  ingest:
    steps: [fetch, transform, publish]
    on_error:
      steps: [cleanup]
```

`on_error` gives explicit recovery flow instead of hidden implicit retries.

## 9) Launcher with fixed bindings

```yaml
launchers:
  fast_mode:
    title: Fast run
    use: ingest
    with:
      mode: fast
      retries: 1
```

Fixed bindings reduce form noise and make safe presets for common run modes.
