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
