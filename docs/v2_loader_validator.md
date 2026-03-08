# V2 Step 4: Loader + Import Resolver + Structural Validator

Реализовано на шаге 4:

- Загрузка v2 YAML-документа из файла (`load_yaml_file`, `load_v2_document`).
- Рекурсивное разрешение `imports` с детекцией циклов в import graph.
- Привязка `source_path` и `base_dir` для каждого загруженного документа.
- Преобразование raw YAML в модели v2 (`V2Document`, `CommandDef`, `PipelineDef`, `LauncherDef`, `StepSpec`, `ForeachSpec`, `OnErrorSpec` и др.).
- Хранение загруженных импортированных документов в `V2Document.imported_documents`.
- Базовая структурная валидация через `validate_v2_document`.

## Что считается валидным на шаге 4

- `version == 2`.
- Root-документ содержит непустой `launchers`.
- Imported документы не содержат `profiles` и `launchers`.
- Имена `commands` и `pipelines` не пересекаются в одном документе.
- `locals` не ссылаются на local, объявленный ниже (`$locals.name`, `${locals.name}`).
- `commands` имеют `run.program` и `run.argv` (list).
- `pipelines` имеют `steps` (list), шаги валидной формы.
- Expanded step не может содержать одновременно `use` и `foreach`.
- `foreach` требует `in`, непустой `as` и непустой `steps`.
- `launcher` требует непустые `title` и `use`.
- `on_error` (если задан) требует непустой `steps`.

## Что intentionally deferred

- Полная валидация expression language.
- Глубокая runtime-семантика `use` по namespaces/import aliases.
- Детальная валидация secrets/vault.
- Полная семантика argv DSL.
- Валидация `when` выражений.
- Разрешение неоднозначностей `$name`.
- Полная валидация stdout/stderr режимов runtime.
