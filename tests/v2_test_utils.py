from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from yaml_cli_ui.v2.context import build_runtime_context
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.models import V2Document

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "v2"


def fixture_path(name: str) -> Path:
    return FIXTURES_DIR / name


def _apply_replacements_to_yaml_tree(root: Path, replacements: Mapping[str, str]) -> None:
    if not replacements:
        return
    for yaml_path in root.rglob("*.yaml"):
        content = yaml_path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            content = content.replace(old, new)
        yaml_path.write_text(content, encoding="utf-8")


def load_fixture_document(
    name: str,
    *,
    replacements: Mapping[str, str] | None = None,
) -> V2Document:
    """Load fixture document with optional replacements over copied fixture subtree."""

    if not replacements:
        return load_v2_document(fixture_path(name))

    with tempfile.TemporaryDirectory(prefix="v2-fixtures-") as tmpdir:
        copied_root = Path(tmpdir) / "v2"
        shutil.copytree(FIXTURES_DIR, copied_root)
        _apply_replacements_to_yaml_tree(copied_root, replacements)
        return load_v2_document(copied_root / name)


def load_fixture_doc(name: str) -> V2Document:
    return load_fixture_document(name)


def runtime_context(
    doc: V2Document,
    *,
    params: dict[str, Any] | None = None,
    selected_profile_name: str | None = None,
    run: dict[str, Any] | None = None,
    with_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = build_runtime_context(
        doc,
        params=params or {},
        selected_profile_name=selected_profile_name,
        run=run,
        with_values=with_values,
    )
    return ctx.as_mapping()


def py_inline(code: str) -> tuple[str, list[str]]:
    return sys.executable, ["-c", code]
