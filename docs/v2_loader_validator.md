# V2 Step 4: loader + import resolver + structural validator

## Implemented in this step

- `yaml_cli_ui.v2.loader` now loads YAML files, builds `V2Document`, resolves recursive imports, tracks `source_path`/`base_dir`, and detects cyclic import graphs.
- Imported documents are stored in-memory under `V2Document.imported_documents` and kept separate from root runtime-only sections.
- `yaml_cli_ui.v2.validator` now validates required v2-lite structural invariants for document version, root launchers, imported-document constraints, callable namespace conflicts, locals ordering, commands, pipelines, foreach/on_error blocks, and launchers.

## What is considered valid/invalid in step 4

Valid:
- `version: 2` document.
- Root document with non-empty `launchers`.
- Imports as `alias -> path string`, recursively resolvable without cycles.
- Imported docs containing only allowed runtime-bearing sections (`imports`, `locals`, `commands`, `pipelines`, plus optional `params`).
- Command definitions with `run.program` and list `run.argv`.
- Pipeline step items as short string steps, expanded `use` steps, or `foreach` steps.

Invalid:
- Non-map YAML root.
- Missing import file or cyclic imports.
- Imported docs with `profiles` or `launchers`.
- Overlapping names between `commands` and `pipelines` in one document.
- Locals referencing future locals via `$locals.name` / `${locals.name}`.
- Step blocks with both `use` and `foreach` (or neither).
- `foreach` missing `in`, `as`, or non-empty `steps`.
- `on_error` with empty steps.

## Deferred intentionally

Not implemented yet in this step:
- Expression language semantics and deep expression typing/validation.
- Full callable-use resolution semantics across imported namespaces.
- Runtime/executor behavior and renderer integration.
- Full argv DSL semantics, secret backend validation depth, and complete `when` validation.
