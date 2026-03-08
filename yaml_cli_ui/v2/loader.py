"""YAML loading and import resolution for YAML CLI UI v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import V2LoadError
from .models import V2Document
from .validator import validate_v2_document
from .builders import build_v2_document


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load YAML from ``path`` and return a mapping root."""

    yaml_path = Path(path).expanduser().resolve()
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise V2LoadError(f"v2 document file not found: {yaml_path}") from exc
    except OSError as exc:
        raise V2LoadError(f"failed to read v2 document file: {yaml_path}") from exc
    except yaml.YAMLError as exc:
        raise V2LoadError(f"failed to parse YAML file {yaml_path}: {exc}") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise V2LoadError(f"v2 document root must be a mapping in file: {yaml_path}")
    return loaded


def _parse_import_map(raw_doc: dict[str, Any], source_path: Path) -> dict[str, str]:
    imports_raw = raw_doc.get("imports", {})
    if imports_raw is None:
        return {}
    if not isinstance(imports_raw, dict):
        raise V2LoadError(f"field 'imports' must be a mapping in file: {source_path}")

    parsed: dict[str, str] = {}
    for alias, value in imports_raw.items():
        if not isinstance(alias, str) or not alias.strip():
            raise V2LoadError(f"import alias must be non-empty string in file: {source_path}")
        if alias in parsed:
            raise V2LoadError(f"duplicate import alias '{alias}' in file: {source_path}")
        if not isinstance(value, str) or not value.strip():
            raise V2LoadError(
                f"import path for alias '{alias}' must be non-empty string in file: {source_path}"
            )
        parsed[alias] = value
    return parsed


def resolve_imports(path: str | Path, *, _stack: tuple[Path, ...] = ()) -> V2Document:
    """Recursively load a v2 document and its import graph."""

    source_path = Path(path).expanduser().resolve()
    if source_path in _stack:
        cycle = " -> ".join(str(p) for p in (*_stack, source_path))
        raise V2LoadError(f"import cycle detected: {cycle}")

    raw_doc = load_yaml_file(source_path)
    import_map = _parse_import_map(raw_doc, source_path)

    imported_documents: dict[str, V2Document] = {}
    for alias, import_ref in import_map.items():
        import_path = (source_path.parent / import_ref).resolve()
        if not import_path.exists():
            raise V2LoadError(
                f"import file for alias '{alias}' does not exist: {import_path} "
                f"(declared in {source_path})"
            )
        imported_documents[alias] = resolve_imports(import_path, _stack=(*_stack, source_path))

    return build_v2_document(
        raw_doc=raw_doc,
        source_path=source_path,
        imported_documents=imported_documents,
    )


def load_v2_document(path: str | Path) -> V2Document:
    """Load, resolve imports and validate a root v2 document."""

    doc = resolve_imports(path)
    validate_v2_document(doc)
    return doc
