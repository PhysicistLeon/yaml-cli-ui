# V2 migration scaffold plan (step 2)

## Status

- Current `yaml_cli_ui/app.py`, `yaml_cli_ui/engine.py`, and `yaml_cli_ui/presets.py` remain **legacy v1** and are intentionally untouched.
- New development branch is introduced in `yaml_cli_ui/v2/` as a separate package scaffold.

## Added v2 modules

- `yaml_cli_ui/v2/models.py` — minimal typed dataclass models for v2 terms.
- `yaml_cli_ui/v2/loader.py` — YAML loading entry point and import-resolution interface.
- `yaml_cli_ui/v2/validator.py` — cheap/safe validation checks for document version and launchers section.
- `yaml_cli_ui/v2/errors.py` — dedicated v2 exception hierarchy.
- `yaml_cli_ui/v2/results.py` — runtime result skeleton (`StepStatus`, `StepResult`, `PipelineResult`).
- `yaml_cli_ui/v2/expr.py` — expression evaluation placeholder.
- `yaml_cli_ui/v2/renderer.py` — rendering placeholder.
- `yaml_cli_ui/v2/executor.py` — execution placeholder.
- `yaml_cli_ui/v2/__init__.py` — stable public exports for initial integration (`V2Document`, `load_v2_document`, `validate_v2_document`).

## Intentionally not implemented yet

- full imports graph resolution and namespacing
- complete schema validation for commands/pipelines/launchers
- expression parser/runtime semantics
- renderer/runtime bindings
- execution engine and process orchestration

All deferred parts currently use explicit `NotImplementedError` placeholders where applicable.

## Developer note for later UI extraction

From legacy `app.py`, the following parts are planned to be extracted into reusable modules in later steps (not in this scaffold):

- form widgets
- field binding
- log tabs
- run history

## Step 3: v2 internal data models

The `yaml_cli_ui/v2/models.py` module now defines a stable dataclass-based core for v2-lite:
- document: `V2Document`
- definitions: `ImportDef`, `ProfileDef`, `ParamDef`, `CommandDef`, `PipelineDef`, `LauncherDef`
- execution shape: `RunSpec`, `StepSpec`, `ForeachSpec`, `OnErrorSpec`
- runtime/result containers: `RunContext`, `StepResult`, `ErrorContext`
- enums: `ParamType`, `SecretSource`, `StepKind`, `StepStatus` (and reserved `ArgvItemKind`)

Core fields are intentionally strict where cheap invariants help (`RunSpec.program`, launcher required fields, non-empty foreach/on_error step lists) and intentionally permissive where later stages need flexibility (`locals: dict[str, Any]`, `argv: list[Any]`, expression-bearing fields typed as `Any`).

Not modeled deeply yet: full YAML parsing rules, import graph resolution, expression evaluation semantics, argv DSL typing/validation, and execution orchestration details.
