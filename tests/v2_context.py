"""Shared v2 test context builders."""

from __future__ import annotations

from pathlib import Path


def build_v2_context(tmp_path: Path) -> dict:
    """Build a baseline v2 runtime context used by expression/renderer tests."""

    return {
        "params": {
            "source_url": "https://example.com",
            "collection": "incoming",
            "mode": "video",
            "jobs": [{"source_url": "a"}, {"source_url": "b"}],
            "count": 5,
            "max_items": 10,
        },
        "locals": {
            "urls_file": str(tmp_path / "urls.json"),
            "run_root": "/tmp/run_1",
        },
        "profile": {"workdir": "/work"},
        "run": {"id": "run_123"},
        "steps": {"scrape": {"stdout": "ok", "exit_code": 0}},
        "loop": {"index": 0},
        "error": {"message": "boom"},
    }
