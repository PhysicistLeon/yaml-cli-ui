# YAML CLI UI v2: Expression engine and template renderer

## Supported expression syntax

`yaml_cli_ui.v2.expr.evaluate_expression()` evaluates expressions with AST allowlist (no `eval()`).

Supported:
- literals: `null`, `true`, `false`, numbers, strings;
- boolean ops: `and`, `or`, `not`;
- comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`;
- dotted access: `params.collection`, `steps.scrape.exit_code`;
- index access: `params.jobs[0].source_url`;
- list/tuple/dict literals;
- allowlisted functions only:
  - `len(x)`
  - `empty(x)`
  - `exists(path)`

Intentionally not supported:
- arbitrary function calls;
- imports/lambda/comprehensions;
- slices and other AST nodes outside allowlist.

## Name resolution

Supported namespaces in context:
- `params`, `locals`, `profile`, `steps`, `run`, `loop`, `error`.

Short names are allowed only when unambiguous:
- if both `params.urls_file` and `locals.urls_file` exist, `$urls_file` raises `V2ExpressionError`;
- explicit references (`$params.urls_file`, `$locals.urls_file`) are always preferred.

## Template rendering

`yaml_cli_ui.v2.renderer` provides:
- `render_value(value, context)`;
- `render_scalar_or_ref(value, context)`;
- `render_string(template, context)`.

Rules:
- non-string values are returned unchanged;
- full-reference strings (`$params.jobs`) return native values (list/int/etc);
- interpolation `${expr}` inside larger strings always returns string chunks;
- interpolation value `None` becomes empty string.

Escaping:
- `$$` -> literal `$`
- `$${` -> literal `${`

## Local reference extraction

`extract_local_refs(value: str) -> set[str]` extracts local names from:
- `$locals.name`
- `${locals.name}`

This utility is designed for validator local-order checks, not as full static analysis.
