# YAML CLI UI

Python app that loads a workflow YAML, generates a form, and executes CLI pipelines with safe argv handling (`shell=False` by default).

## Run

```bash
python main.py examples/sample.yaml
```

## Highlights

- YAML is single source of truth for UI + execution.
- Supports `run`, nested `pipeline`, `foreach`.
- Expression templates `${...}` with safe AST evaluation.
- Deterministic argv serialization (strings, short maps, extended option objects).
- Stores `step.<id>.exit_code/stdout/stderr/duration_ms`.
- Reload button for quick YAML switching.

## Notes

- For `multichoice`, `kv_list`, `struct_list`, and `path` with `multiple=true`, enter JSON in text boxes.
- `secret` with `source: env` pulls value from OS environment variable.
