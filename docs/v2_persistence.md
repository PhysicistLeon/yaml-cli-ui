# V2 launcher persistence

V2 uses dedicated launcher-aware storage files next to the source YAML:

- presets: `<config>.launchers.presets.json`
- UI/session state: `<config>.state.json`

This intentionally differs from legacy v1 `<config>.presets.json` and does not auto-migrate v1 data.

## Storage split

- Presets file stores only named launcher presets (`launchers -> presets -> params`).
- State file stores operational UI state (`selected_profile`, `last_values`, `last_selected_preset`).

## Secret sanitization

`secret` params are never persisted to disk (presets or state).

Additional conservative rule in this step:

- values from `launcher.with` are not persisted in `last_values`, because they are fixed by config and read-only in launcher dialogs.

## Value precedence in launcher dialog

When opening launcher form, values are applied in this order:

1. root param defaults
2. `state.launchers.<name>.last_values`
3. selected preset values
4. `launcher.with` fixed values (highest priority, read-only)

Unknown/removed fields in presets/state are ignored.

Launcher dialog structure (EBNF-like):

- `LauncherDialog := PresetBar ParamFields UnusedPresetFieldsWarning Actions`
- `PresetBar := preset_selector apply save/create overwrite rename delete`
- `NumericSliderField := slider current_value_display bound_numeric_variable`
- `PresetApply := preset values -> editable fields; ignore unknown; never override launcher.with`

When a preset contains fields that are no longer editable for the launcher,
they are ignored during apply and shown in the dialog compatibility block
(`Unused preset fields`).

Numeric params support slider widgets in v2 launcher forms:

- explicit: `widget: "slider"` for `int`/`float`
- implicit fallback: `min` + `max` can render a slider when `widget` is omitted
- explicit non-slider widget keeps non-slider rendering (explicit `widget` has priority)

Slider normalization is deterministic for init/apply/collect paths:

- values are clamped to `[min, max]`
- values are snapped to `step` (with safe fallback when `step <= 0`)
- `int` sliders return `int`, `float` sliders return `float`

## Not implemented by design in this step

- automatic v1 -> v2 storage migration
- cloud sync / shared remote persistence
- vault file format design


## Error fallback and warnings

On malformed/broken v2 persistence files, the service uses safe defaults (empty presets/state)
instead of crashing the app, and accumulates warnings in `LauncherPersistenceService.warnings`
(`last_warning` remains available as a convenience alias).

`AppV2` shows one aggregated warning message per reload when such warnings exist.

## Editable-value filtering consistency

The same editable filter is applied when reading `last_values` and applying presets:

- unknown fields are ignored
- secret params are ignored
- `launcher.with` params are ignored

This keeps restored/applied values aligned with launcher editable fields only.
