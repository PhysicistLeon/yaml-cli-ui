# yaml-cli-ui

YAML-driven CLI pipeline engine with dynamic Tkinter UI.

## Features

- Loads `version: 1` YAML with `app`, `vars`, `actions` sections.
- Generates action form dynamically from field definitions.
- Supports templates `${...}`, safe expression evaluation, conditional steps.
- Executes `run`, nested `pipeline`, and `foreach` steps.
- Serializes argv deterministically without shell-style splitting.
- Stores per-step `exit_code`, `stdout`, `stderr`, `duration_ms`.
- Windows-friendly defaults: `shell=False`, raw argv passing.

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
yaml-cli-ui examples.yaml
```

## Notes

- Reload button re-reads YAML at runtime.
- For `kv_list` / `struct_list`, UI expects JSON array input.
