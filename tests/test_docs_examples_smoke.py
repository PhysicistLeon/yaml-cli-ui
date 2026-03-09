from __future__ import annotations

from pathlib import Path

from yaml_cli_ui.bootstrap import detect_yaml_version
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.persistence import get_v2_presets_path, get_v2_state_path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_examples_files_exist() -> None:
    expected = [
        REPO_ROOT / "examples" / "yt_audio.yaml",
        REPO_ROOT / "examples" / "v1_minimal.yaml",
        REPO_ROOT / "examples" / "v2_minimal.yaml",
        REPO_ROOT / "examples" / "v2_ingest_demo.yaml",
        REPO_ROOT / "examples" / "packs" / "v2_media_pack.yaml",
    ]
    for path in expected:
        assert path.exists(), f"missing expected example file: {path}"


def test_v2_examples_load_and_validate() -> None:
    for rel in ("examples/v2_minimal.yaml", "examples/v2_ingest_demo.yaml"):
        doc = load_v2_document(REPO_ROOT / rel)
        assert doc.version == 2
        assert doc.launchers


def test_v1_example_routes_to_legacy_version() -> None:
    assert detect_yaml_version(REPO_ROOT / "examples" / "yt_audio.yaml") == 1
    assert detect_yaml_version(REPO_ROOT / "examples" / "v1_minimal.yaml") == 1


def test_documented_v2_persistence_paths() -> None:
    config_path = REPO_ROOT / "examples" / "v2_minimal.yaml"
    assert get_v2_presets_path(config_path).name.endswith(".launchers.presets.json")
    assert get_v2_state_path(config_path).name.endswith(".state.json")


def test_readme_mentions_supported_versions() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "version: 1" in readme
    assert "version: 2" in readme
