# v2 step 6: locals & runtime context

This step implements **only** locals evaluation and runtime context assembly for v2.

## Profile selection

`resolve_selected_profile(...)` behavior:
- explicit `selected_profile` wins;
- else `selected_profile_name` is resolved from `doc.profiles`;
- else no profiles => `{}`;
- else single profile => auto-selected;
- else execution error (ambiguous profile selection).

## Locals evaluation

`evaluate_root_locals(...)` evaluates `doc.locals` strictly top-to-bottom.

A local can reference:
- `params.*`
- `profile.*`
- already evaluated `locals.*`
- imported `alias.locals.*`
- `run.*`

For this step, locals evaluation context intentionally excludes `steps`, `loop`, `error`.

## Runtime context shape

`build_runtime_context(...)` returns `RunContext` with namespaces:
- `params`
- `locals`
- `profile`
- `run`
- `steps`
- optional `loop`
- optional `error`
- imported aliases (`alias -> {locals: ...}`)

`RunContext.as_mapping()` exposes a plain mapping for renderer/expression usage.

## with-values bindings

`with_values` are added as short-name bindings:
- `$collection` may resolve from `with_values["collection"]`;
- explicit namespaces are unchanged (`$params.collection`, `$locals.x`, etc.).

Short-name candidates are searched in:
`with_values`, `params`, `locals`, `run`, `loop`, `error`.

Ambiguous short names remain errors.

## Imported locals

Imported documents are evaluated recursively and exposed only under aliases:
- `$media.locals.scrape_script`
- `$fs.locals.ensure_dir_script`

Imported locals are **not** auto-merged into root `locals`.

## Not implemented in this step

- argv serializer
- command executor
- pipeline executor
- real step result population
- foreach runtime execution
- on_error runtime execution
- UI wiring
- presets/state persistence
