# AppV2 UI (step 11)

В этом шаге добавлен launcher-oriented UI для `version: 2` рядом с legacy `App` (v1).

## Что вынесено из legacy `app.py`

- Общие статусы/цвета кнопок в `yaml_cli_ui/ui/status.py`.
- Переиспользуемая форма параметров в `yaml_cli_ui/ui/form_widgets.py`.
- Рендеринг `StepResult` и лог-вкладки в `yaml_cli_ui/ui/log_views.py`.
- In-memory история запусков в `yaml_cli_ui/ui/history.py`.

Legacy `App` сохранён и продолжает работать по старому пути.

## Что такое AppV2

`yaml_cli_ui/app_v2.py` содержит новый `AppV2`:

- загружает/валидирует v2 YAML через `load_v2_document`;
- рендерит top-level `launchers` как кнопки;
- поддерживает profile selection (none/one/many);
- строит launcher dialog по root `params`;
- использует консервативный режим полей: показываются все root params, кроме полностью фиксированных в `launcher.with`;
- `launcher.with` показывается read-only;
- запуск выполняется в background thread;
- результат (`StepResult`) рендерится в aggregate/per-launcher логи и in-memory history.

## LauncherDialog

- editable params
- fixed/read-only with-bound params
- validation required/must_exist
- submit -> background execution

## Что специально не реализовано в этом шаге

- persistence layer для v2 launchers/history/status
- миграция legacy presets/state
- parallel execution
- «полный новый UI framework»

История/статусы AppV2 хранятся только в памяти UI-сессии.
