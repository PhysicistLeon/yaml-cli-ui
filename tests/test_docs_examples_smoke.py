from __future__ import annotations

from pathlib import Path

from yaml_cli_ui.bootstrap import detect_yaml_version
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.persistence import get_v2_presets_path, get_v2_state_path


def test_examples_files_exist():
    assert Path("examples/yt_audio.yaml").exists()
    assert Path("examples/v1_yt_audio.yaml").exists()
    assert Path("examples/v2_minimal.yaml").exists()
    assert Path("examples/v2_ingest_demo.yaml").exists()


def test_v2_examples_load_and_validate():
    minimal = load_v2_document("examples/v2_minimal.yaml")
    ingest = load_v2_document("examples/v2_ingest_demo.yaml")

    assert minimal.version == 2
    assert ingest.version == 2
    assert "ingest_default" in ingest.launchers


def test_v1_example_still_routes_to_legacy_version():
    assert detect_yaml_version("examples/yt_audio.yaml") == 1
    assert detect_yaml_version("examples/v1_yt_audio.yaml") == 1


def test_documented_v2_persistence_filenames():
    cfg_path = Path("examples/v2_minimal.yaml")

    assert get_v2_presets_path(cfg_path).name == "v2_minimal.yaml.launchers.presets.json"
    assert get_v2_state_path(cfg_path).name == "v2_minimal.yaml.state.json"


def test_docs_mention_supported_versions_and_migration_docs():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "version: 1" in readme
    assert "version: 2" in readme
    assert "docs/v2_spec.md" in readme
    assert "docs/v1_to_v2_migration.md" in readme
    assert "docs/v2_examples.md" in readme
