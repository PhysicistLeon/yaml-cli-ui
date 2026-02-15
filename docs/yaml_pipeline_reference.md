# YAML Pipeline Reference (v1, as-implemented)

CLI YAML Pipeline Engine is a **Python application** that:

* Loads a YAML file describing a CLI-driven workflow.
* Shows top-level actions as a set of quick-launch buttons.
* Opens a modal parameter dialog for the selected action and collects user inputs.
* Executes a **pipeline of CLI steps**.
* Safely constructs subprocess calls using an **argv list (NOT shell strings)**.
* Supports batch operations, conditional steps, and reusable variables.


В текущей реализации многие ключевые правила жёстко определяются кодом:

1. **Поддерживается только `version: 1`**.
2. **`actions` обязателен** и должен быть непустым map.
3. Action обязан иметь `title` и хотя бы одно из: `pipeline` или `run`.
4. Если у action есть только `run`, движок автоматически оборачивает его в одношаговый pipeline.
5. Типы шагов ограничены: `run`, `pipeline`, `foreach`.
6. Шаблоны рендерятся только в строках; non-string значения возвращаются как есть.
7. Expression evaluator ограничен allowlist-ом AST-узлов и разрешает вызовы только `len`, `empty`, `exists`.
8. Алиас `program: python` может быть переопределён через `runtime.python.executable`.

## 3) Минимальная структура YAML

```yaml
version: 1

app:
  shell: false
  workdir: "C:\\work"
  env:
    PYTHONUNBUFFERED: "1"

runtime:
  python:
    executable: "C:\\venv\\Scripts\\python.exe"

vars:
  repo: "C:\\work\\project"

actions:
  do_job:
    title: "Run job"
    pipeline:
      - id: step1
        run:
          program: python
          argv:
            - "script.py"
```

---

## 4) Шаблонизатор `${...}`: фактическая семантика

## 4.1 Где рендерится

`render_template(...)` применяется в местах, где движок это явно делает:

- значения `vars` (при построении базового контекста);
- `when` выражения шагов;
- `run.program`, `run.workdir`, `run.env.*`;
- элементы `run.argv` (включая short-map/extended-option формы);
- `runtime.python.executable` (когда `program == "python"`).

## 4.2 Полное совпадение vs встраивание

- Если строка целиком `${expr}` → возвращается **тип результата выражения** (bool/list/число/строка и т.д.).
- Если `${expr}` встроено внутрь строки → подставляется `str(result)`.
- Если `result is None` → подставляется пустая строка.

## 4.3 Контекст выражений

В выражениях доступны:

- `vars`
- `form`
- `env`
- `step`
- `cwd`, `home`, `temp`, `os`
- функции: `len`, `empty`, `exists`

`vars/form/env/step` доступны как dot-style (`vars.repo`) и индексно (`form["x"]`) через `DotDict`.

## 4.4 Ограничения expression language

Разрешены только AST-конструкции из allowlist (Expression/Name/Constant/Attribute/BoolOp/UnaryOp/Compare/Call/Subscript/List/Tuple/Dict и т.д.).

Вызовы функций разрешены **только** для имён:

- `len(...)`
- `empty(...)`
- `exists(...)`

Любые другие вызовы блокируются.

---

## 5) `vars`: порядок разрешения и неочевидные эффекты

`vars` вычисляются в `_base_context` в 2 этапа:

1. Сбор исходных значений:
   - если var описан как map с `default`, берётся `default`;
   - иначе берётся значение var как есть.
2. Один проход `render_template` по каждому var.

### Важно: один проход без рекурсивной стабилизации

Это означает:

- вложенные зависимости между vars чувствительны к порядку и могут оставлять неразрешённые `${...}` внутри строки;
- второй автоматический проход по результату не делается.

Практический вывод: для критичных путей лучше строить итоговую строку напрямую, без глубокой цепочки `vars.* -> vars.* -> vars.*`.

---

## 6) Pipeline шаги

## 6.1 Общие поля шага

У любого шага могут быть:

- `id` (если нет, генерируется `step_<n>`)
- `when` (если false → шаг пропускается)
- `continue_on_error` (если true, ошибка шага логируется как warning и пайплайн продолжается)

## 6.2 `run`

```yaml
- id: run_ps
  run:
    program: "powershell"
    workdir: "${vars.repo}"
    shell: false
    timeout_ms: 30000
    env:
      FOO: "bar"
    argv:
      - "-NoProfile"
      - "-Command"
      - "Write-Host hello"
    stdout: "capture"
    stderr: "capture"
```

Фактические default-ы:

- `shell`: `run.shell` или fallback на `app.shell` (иначе `false`)
- `workdir`: `run.workdir` или fallback на `app.workdir`
- `stdout/stderr`:
  - если `capture` не указан или `true` → default `capture`
  - если `capture: false` → default `inherit`
- `stdout/stderr: file:<path>` записывает накопленный вывод в файл.

## 6.3 `pipeline` (nested)

```yaml
- id: phase_a
  pipeline:
    - id: a1
      run: ...
    - id: a2
      run: ...
```

Вложенные шаги выполняются последовательно тем же движком.

## 6.4 `foreach`

```yaml
- id: per_item
  foreach:
    in: "${vars.items}"
    as: item
    steps:
      - id: do_one
        run:
          program: "python"
          argv:
            - "worker.py"
            - "--name"
            - "${item.name}"
```

Требования:

- `foreach.in` после рендера должен быть list, иначе ошибка;
- в scope каждой итерации доступны:
  - переменная из `as` (по умолчанию `item`)
  - `loop.index`.

---

## 7) `argv` сериализация (ключевой power-user раздел)

Движок поддерживает 3 формы записи элементов `argv`.

## 7.1 String

```yaml
argv:
  - "literal"
  - "${vars.path}"
```

Результат: каждый элемент становится отдельным argv-токеном.

## 7.2 Short-map (single-key dict без `opt`)

```yaml
argv:
  - "script.py"
  - "--name": "${vars.user}"
  - "--verbose": "${form.verbose}"
```

Правила:

- `true`  -> добавить только опцию (`--flag`)
- `false`/`None`/`""` -> пропустить
- list -> повторить пару `opt value` для каждого элемента
- остальное -> `opt value`

## 7.3 Extended option (`opt`-форма)

```yaml
argv:
  - opt: "--langs"
    from: "${vars.langs}"
    mode: join
    joiner: ","
```

Поддерживаемые поля:

- `opt` (обязательно)
- `from`
- `when`
- `mode`: `auto|flag|value|repeat|join`
- `style`: `separate|equals`
- `omit_if_empty` (default `true`)
- `template`
- `false_opt`
- `joiner` (для `join`)

### Реальное поведение `mode`

- `auto`:
  - bool -> `flag`
  - list -> `repeat`
  - иначе -> `value`
- `flag`:
  - `true` -> `opt`
  - `false` + `false_opt` -> `false_opt`
- `value` -> один `opt value`
- `repeat` -> для каждого элемента отдельный `opt value`
- `join` -> один `opt` + строка, склеенная через `joiner`

### Специальный tri-state string в `opt`-форме

Если значение после рендера строка из `{"auto","true","false"}`:

- `"auto"` -> опция пропускается
- `"true"` -> добавляется `opt`
- `"false"` -> добавляется `false_opt` (если задан)

Это работает даже без явного `mode: flag`.

### `style`

- `separate` (default): `--opt value`
- `equals`: `--opt=value`

---

## 8) Windows-практика (PowerShell + пути)

## 8.1 Рекомендуемый базовый шаблон для PowerShell

```yaml
run:
  program: "powershell"
  argv:
    - "-NoProfile"
    - "-Command"
    - >
      $src='${vars.src}';
      $dst='${vars.dst}';
      Copy-Item -LiteralPath $src -Destination $dst -Force
```

## 8.2 Пути

- В double-quoted YAML строках экранируйте backslash как `\\`.
- В блок-строках (`|` или `>`) можно писать PowerShell-команду более читаемо.
- Для `explorer.exe` передавайте путь отдельным argv-элементом:

```yaml
run:
  program: "explorer.exe"
  argv:
    - "${vars.target_dir}"
```

---

## 9) Anti-patterns

1. **Глубокие цепочки vars-зависимостей**

```yaml
vars:
  a: "C:\\x"
  b: "${vars.a}\\y"
  c: "${vars.b}\\z"
```

Риск: из-за одношаговой подстановки часть `${...}` может остаться literal.

2. **Склейка всей команды в один string при `shell: false`**

```yaml
argv:
  - "python script.py --x 1 --y 2"
```

Это один argv-токен, а не разбор shell.

3. **Short-map с неоднозначными типами**

```yaml
- "--flag": "false"
```

Строка `"false"` в short-map не равна bool `False`; получите `--flag false`, а не пропуск.

4. **Ожидание рекурсивного рендера `${...}` внутри уже отрендеренных vars**

Движок не делает повторных проходов до стабилизации.

5. **Смешивание `style: equals` с программой, которая не принимает `--opt=value`**

Убедитесь, что CLI реально поддерживает equals-форму.

---

## 10) Известные ограничения и подводные камни

1. **Нет рекурсивного/многошагового resolve vars**.
2. **Порядок вычисления vars влияет на итог** (итерация по map).
3. **`foreach.in` обязан дать list**, другие iterable не принимаются.
4. **Expression calls ограничены** (`len/empty/exists`), пользовательские функции нельзя.
5. **Template-render только для string-значений**; объекты/числа не рендерятся «вглубь» сами по себе.
6. **`program: python` переопределяется только при точном совпадении строки `python`**.

---

## 11) Готовые шаблоны

## 11.1 Python + runtime override

```yaml
version: 1
runtime:
  python:
    executable: "C:\\code\\Python\\.venvs\\stable\\Scripts\\python.exe"

actions:
  run_script:
    title: "Run script"
    pipeline:
      - id: run
        run:
          program: "python"
          workdir: "C:\\repo"
          argv:
            - "task.py"
            - "--input"
            - "C:\\repo\\input.txt"
```

## 11.2 PowerShell copy artifact

```yaml
version: 1
vars:
  repo: "C:\\_SYNC\\Code\\Python\\WebScraping\\ecom"
  src_xlsx: "${vars.repo}\\result.xlsx"
  dst_xlsx: "${vars.repo}\\video_table_webview\\result.xlsx"

actions:
  copy_result:
    title: "Copy result.xlsx"
    pipeline:
      - id: copy
        run:
          program: "powershell"
          workdir: "${vars.repo}"
          argv:
            - "-NoProfile"
            - "-Command"
            - >
              $src='${vars.src_xlsx}';
              $dst='${vars.dst_xlsx}';
              if (-not (Test-Path -LiteralPath $src)) { throw "Source not found: $src" }
              Copy-Item -LiteralPath $src -Destination $dst -Force
```

## 11.3 Conditional + foreach

```yaml
version: 1
vars:
  names:
    - { name: "alpha" }
    - { name: "beta" }

actions:
  batch:
    title: "Batch run"
    pipeline:
      - id: loop
        foreach:
          in: "${vars.names}"
          as: item
          steps:
            - id: per_item
              when: "${item.name != ''}"
              run:
                program: "python"
                argv:
                  - "worker.py"
                  - "--name": "${item.name}"
```

## 11.4 explorer.exe open folder

```yaml
version: 1
vars:
  out_dir: "C:\\repo\\video_table_webview"

actions:
  open_folder:
    title: "Open folder"
    run:
      program: "explorer.exe"
      argv:
        - "${vars.out_dir}"
```

