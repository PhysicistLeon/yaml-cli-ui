# YAML CLI UI

Python app that loads workflow YAML, builds a dynamic form, serializes argv deterministically, and executes CLI pipelines with safe `subprocess.run(..., shell=False)` defaults.

## Run

```bash
python main.py examples/yt_audio.yaml
```

## Features

- Dynamic action/forms from YAML.
- Supported steps: `run`, nested `pipeline`, `foreach`.
- Safe expression evaluator for `${...}` templates.
- Deterministic argv serialization (string/short-map/extended-option forms).
- Step result storage (`exit_code/stdout/stderr/duration_ms`).
- YAML reload button in UI.


## Runtime aliases

You can define runtime-level executable overrides, for example for Python:

```yaml
runtime:
  python:
    executable: "C:\\code\\Python\\.venvs\\stable3_12_4\\Scripts\\python.exe"

actions:
  run_script:
    title: "Run Python script"
    pipeline:
      - id: run
        run:
          program: python
          argv:
            - "scripts\\process.py"
```

When `program: python` is used in a step, the configured `runtime.python.executable` is used instead.
