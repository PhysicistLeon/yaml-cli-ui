"""YAML loading and import-resolution scaffold for YAML CLI UI v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import V2LoadError
from .models import LauncherDef, V2Document


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return mapping-like root object."""

    yaml_path = Path(path)
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise V2LoadError(f"v2 document file not found: {yaml_path}") from exc
    except OSError as exc:
        raise V2LoadError(f"failed to read v2 document file: {yaml_path}") from exc
    except yaml.YAMLError as exc:
        raise V2LoadError(f"failed to parse YAML document: {yaml_path}") from exc

    if not isinstance(loaded, dict):
        raise V2LoadError("v2 document root must be a mapping")
    return loaded


def resolve_imports(raw_doc: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """Resolve imports section for v2 documents (not implemented in scaffold step)."""

    if raw_doc.get("imports"):
        raise NotImplementedError(
            "v2 imports resolution is intentionally deferred in migration scaffold "
            f"(base_dir={base_dir})"
        )
    return raw_doc


def _parse_launchers(raw_doc: dict[str, Any]) -> dict[str, LauncherDef]:
    launchers_raw = raw_doc.get("launchers")
    if not isinstance(launchers_raw, dict):
        return {}

    parsed: dict[str, LauncherDef] = {}
    for name, entry in launchers_raw.items():
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        use = entry.get("use")
        if not isinstance(title, str) or not isinstance(use, str):
            continue
        parsed[name] = LauncherDef(
            title=title,
            use=use,
            info=entry.get("info") if isinstance(entry.get("info"), str) else None,
            with_values=entry.get("with", {}) if isinstance(entry.get("with"), dict) else {},
        )
    return parsed


def load_v2_document(path: str | Path) -> V2Document:
    """Load a v2 YAML document into minimal typed model scaffold."""

    raw_doc = load_yaml_file(path)
    resolved = resolve_imports(raw_doc, Path(path).resolve().parent)
    version = resolved.get("version", 0)
    if not isinstance(version, int):
        raise V2LoadError("v2 document field 'version' must be an integer")

    resolved_path = Path(path).resolve()
    return V2Document(
        raw=resolved,
        version=version,
        launchers=_parse_launchers(resolved),
        source_path=resolved_path,
        base_dir=resolved_path.parent,
    )
