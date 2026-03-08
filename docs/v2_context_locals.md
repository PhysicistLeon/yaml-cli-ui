# V2 step 6: locals + runtime context

This document captures the current v2 scope implemented for context building and locals evaluation.

## Profile selection

`resolve_selected_profile(...)` behavior:

1. If `selected_profile` mapping is passed directly, it is used as-is.
2. Else if `selected_profile_name` is passed, profile is resolved from `doc.profiles`.
3. Else if there are no profiles, an empty profile `{}` is used.
4. Else if there is exactly one profile, it is selected automatically.
5. Else an execution error is raised (caller must select profile explicitly).

## Locals evaluation model

`locals` are evaluated eagerly and strictly top-to-bottom in declaration order.

Each local can reference:

- `params.*`
- `profile.*`
- previously computed `locals.*`
- imported namespaces via `ns.locals.*`
- `run.*`

Locals evaluation intentionally does **not** include or allow runtime `steps/loop/error` namespaces.

## Runtime context shape

`RunContext.as_mapping()` produces a mapping containing:

- root namespaces: `params`, `locals`, `profile`, `run`, `steps`
- optional namespaces: `loop`, `error` (included only when present)
- imported aliases: `{alias: {locals: ...}}`
- short-name bindings bucket: `bindings`

## `with_values` behavior

`with_values` are merged as short-name bindings (`bindings`) and do not overwrite explicit namespaces.

- `$params.collection` always resolves to root params.
- `$locals.x` always resolves to root locals.
- `$collection` can resolve from bindings if unique.

Short-name resolution candidates are: `bindings`, `params`, `locals`, `run`, `loop`, `error`.
Ambiguous names raise expression errors.

## Imported locals

Imported documents are evaluated recursively first. Their locals are exposed only through alias namespaces:

- `$media.locals.scrape_script`
- `$fs.locals.ensure_dir_script`

Imported locals are not auto-merged into root `locals`.

## Not implemented in this step

- argv serialization
- command execution / subprocess runtime
- pipeline runtime
- foreach/on_error execution runtime
- real `steps` results population from execution
- UI integration
- state/preset persistence
