# v2 argv DSL serializer

This document describes the Step 7 serializer layer that turns `RunSpec.argv` into a final `list[str]` for future command execution.

## Supported `argv` item forms

Minimal grammar:

- `Argv := [ArgvItem, ...]`
- `ArgvItem := ScalarItem | OptionMap | ConditionalItem`
- `ScalarItem := string | number | boolean | "$name" | string with `${expr}``
- `OptionMap := { option_name: value }`
- `ConditionalItem := { when: value_or_expr, then: ArgvItem }`

## Serialization behavior

### 1) Scalar item

Examples:

- `"--extract-audio"`
- `"$params.source_url"`
- `0`

Rules:

- Serialized as exactly one argv token.
- No shell splitting (spaces stay inside the same token).
- Item is rendered through v2 renderer first.
- If rendered scalar becomes list/dict/null, serializer raises an error.

### 2) Option map

Example: `{ "--audio-format": "mp3" }`

Rules for `{ key: value }` after rendering value:

- `True` -> `[key]`
- `False` -> `[]`
- `None` -> `[]`
- `""` -> `[]`
- scalar -> `[key, str(value)]`
- list -> repeat option for each list value
- empty list -> `[]`

Important:

- `0` is not empty and becomes `"0"`.
- `"false"` is a string, not bool; result is `[key, "false"]`.

### 3) Conditional item

Example: `{ when: "$params.embed_thumb", then: "--embed-thumbnail" }`

Rules:

- Render/evaluate `when` with existing renderer/context.
- If truthy (Python truthiness), serialize nested `then`.
- If falsy, emit nothing.

Invalid conditional shapes are rejected, for example:

- `{ when: true }`
- `{ then: "--x" }`
- `{ when: true, "--x": 1 }`

## Shape validation

- Dict item with exactly one non-reserved key => option map.
- Dict item with exactly keys `{when, then}` => conditional item.
- Any other dict shape => validation error.

## Intentionally not supported in this step

- subprocess execution
- pipeline execution
- foreach runtime
- on_error runtime
- UI wiring / presets / state

This layer is serializer-only and prepares argv tokens for the next executor step.
