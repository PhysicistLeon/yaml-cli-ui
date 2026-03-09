from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from yaml_cli_ui.v2.context import build_runtime_context, context_to_mapping
from yaml_cli_ui.v2.loader import load_v2_document

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "v2"


def fixture_path(name: str) -> Path:
    return _FIXTURES_DIR / name


def load_fixture_document(name: str, *, replacements: dict[str, str] | None = None):
    source = fixture_path(name)
    if replacements:
        text = source.read_text(encoding="utf-8")
        for key, value in replacements.items():
            text = text.replace(key, value)
        import tempfile

        import os

        fd, name = tempfile.mkstemp(suffix='.yaml', dir=source.parent)
        os.close(fd)
        Path(name).write_text(text, encoding='utf-8')
        tmp_path = Path(name)
        try:
            return load_v2_document(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    return load_v2_document(source)


def portable_python_replacements(tmpdir: Path | None = None) -> dict[str, str]:
    items = {"__PYTHON__": sys.executable}
    if tmpdir is not None:
        items["__TMPDIR__"] = str(tmpdir)
    return items


def runtime_context_mapping(doc, *, params: dict[str, Any] | None = None, profile: str | None = None):
    ctx = build_runtime_context(
        doc,
        params=params or {},
        selected_profile_name=profile,
        run={"id": "test_run"},
    )
    return context_to_mapping(ctx)


def deep_copy_context(context: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(context)
