# V2 argv DSL (step 7)

`RunSpec.argv` in v2 supports a strict mini-DSL for serialization into `list[str]` (for future command executor usage).

## Supported shapes

- **Scalar item**: string / number / boolean / reference or template string.
  - Serialized as exactly **one token**.
  - No shell splitting is performed.
- **Option map**: `{ option_name: value }`
  - Map with exactly one key, key is not `when`/`then`.
- **Conditional item**: `{ when: EXPR_OR_VALUE, then: ITEM }`
  - Map with exactly keys `when` and `then`.
  - `then` currently supports scalar item or option map.

## Option map value semantics

For `{ "--flag": value }`:

- `true` -> `["--flag"]`
- `false` -> `[]`
- `null` -> `[]`
- `""` -> `[]`
- scalar (including `0`) -> `["--flag", str(value)]`
- list -> repeated option pairs (`["--x", "a", "--x", "b"]`)
- empty list -> `[]`

Notes:
- `0` is not considered empty.
- string `"false"` is not boolean false; it is serialized as text.

## Conditional truthiness

`when` uses normal Python-like truthiness after rendering:
`False`, `None`, `0`, `""`, `[]`, `{}` are falsy; everything else is truthy.

## Intentionally unsupported/strict behavior

- Invalid map shapes are rejected with validation errors.
- Standalone scalar item that resolves to `None` is rejected.
- Scalar item resolving to list/dict is rejected.
- Serializer does not execute subprocesses/pipelines and does not build runtime context.
