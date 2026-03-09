from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from yaml_cli_ui.v2.context import build_runtime_context
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.models import V2Document

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "v2"


def fixture_path(name: str) -> Path:
    return FIXTURES_DIR / name


def load_fixture_doc(name: str) -> V2Document:
    return load_v2_document(fixture_path(name))


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
