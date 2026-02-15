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
