# v2: Expression Engine и Template Renderer (шаг 5)

Этот документ фиксирует ограничения и поведение v2 expression/rendering слоя до подключения runtime/executor.

## Поддерживаемые выражения

`evaluate_expression(expr, context)` поддерживает:
- литералы: числа, строки, `true`, `false`, `null`;
- булевы операции: `and`, `or`, `not`;
- сравнения: `==`, `!=`, `<`, `>`, `<=`, `>=`;
- dotted-path доступ (`params.collection`, `steps.scrape.exit_code`);
- index access (`params.jobs[0].source_url`);
- list/tuple/dict литералы;
- вызовы только allowlist-функций.

Поддерживаются и формы `"params.x"`, и обёртка `"${params.x}"`.

## Разрешённые функции

Только функции:
- `len(x)`
- `empty(x)` — `True` для `None` и пустых коллекций/строк
- `exists(path)` — `os.path.exists(...)`

Любые другие вызовы/узлы AST отклоняются с `V2ExpressionError`.

## Namespace и короткие имена

Разрешённые namespaces в context:
- `params`, `locals`, `profile`, `steps`, `run`, `loop`, `error`

Короткая форма `$name` разрешена только при однозначном совпадении между namespace-контейнерами.
Если имя встречается более чем в одном namespace, выбрасывается `V2ExpressionError` и требуется явная форма (`$params.name`, `$locals.name`).

## Template rendering

`render_string(template, context)` поддерживает:
- интерполяции `${expr}`;
- `None` в интерполяции рендерится как `""`;
- `$$` → литерал `$`;
- `$${` → литерал `${`.

`render_scalar_or_ref(value, context)` сохраняет нативные типы для полных ссылок:
- `$params.jobs` → `list`
- `$params.max_items` → `int`
- `$locals.urls_file` → `str`

## Что специально не поддерживается на этом шаге

- runtime/use resolution за пределами уже собранного context;
- executor / subprocess / pipeline runtime;
- foreach execution;
- UI wiring;
- полный static analysis всех возможных ссылок.
