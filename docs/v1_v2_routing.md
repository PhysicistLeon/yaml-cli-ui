# v1/v2 side-by-side config routing

This document describes the smoke integration routing layer that keeps legacy v1 and new v2 running in parallel.

## Routing model

- Supported versions: `1 | 2`
- Routing is explicit and version-based.

EBNF-style summary:

```text
ConfigRouting :=
  read config file
  determine version
  version == 1 -> legacy app path
  version == 2 -> v2 app path
  else -> unsupported version error

SupportedVersions :=
  1 | 2

OpenFlow :=
  startup/open/browse/reload
  -> detect version
  -> select app path
  -> construct correct app
  -> continue normal version-specific flow
```

## Bootstrap API

`yaml_cli_ui/bootstrap.py` exposes a small testable API:

- `detect_yaml_version(path) -> int`
- `select_app_class_for_version(version) -> type`
- `open_app_for_config(path, settings_path=None, root=None) -> object`

Main entrypoint (`main.py`) now goes through this bootstrap module.

## Behavior

- `version: 1` config opens with legacy `App` flow.
- `version: 2` config opens with `AppV2` flow.
- Unsupported/missing/malformed `version` yields a controlled routing error.
- `--settings app.ini` with `[ui] default_yaml` works for both v1 and v2.

Browse/reload side-by-side behavior:

- If a currently running app loads a config of another version, current window is closed and the correct version app is reopened.
- No in-place hot conversion between app classes is attempted.

## Smoke fixtures

- v1 example: `examples/yt_audio.yaml`
- v2 example: `examples/v2_minimal.yaml`

## Intentionally not implemented in this step

- auto-migration of v1 config/storage to v2
- unified persistence across v1/v2
- in-place app-class conversion without reopen
