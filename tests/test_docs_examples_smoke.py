from __future__ import annotations

from pathlib import Path

from yaml_cli_ui.bootstrap import detect_yaml_version
from yaml_cli_ui.v2.loader import load_v2_document
from yaml_cli_ui.v2.persistence import get_v2_presets_path, get_v2_state_path


DOC_FILES = [
    Path("docs/v2_spec.md"),
    Path("docs/v1_to_v2_migration.md"),
    Path("docs/v2_examples.md"),
]

EXAMPLE_FILES = [
    Path("examples/yt_audio.yaml"),
    Path("examples/v1_yt_audio.yaml"),
    Path("examples/v2_minimal.yaml"),
    Path("examples/v2_ingest_demo.yaml"),
    Path("examples/packs/media.yaml"),
    Path("examples/packs/fs.yaml"),
]


def test_docs_and_examples_files_exist():
    for path in [*DOC_FILES, *EXAMPLE_FILES]:
        assert path.exists(), f"Missing expected file: {path}"


def test_v2_examples_load_and_validate():
    minimal = load_v2_document("examples/v2_minimal.yaml")
    ingest = load_v2_document("examples/v2_ingest_demo.yaml")

    assert minimal.version == 2
    assert ingest.version == 2
    assert "ingest_default" in ingest.launchers


def test_v1_examples_route_to_legacy_and_v2_examples_route_to_v2():
    assert detect_yaml_version("examples/yt_audio.yaml") == 1
    assert detect_yaml_version("examples/v1_yt_audio.yaml") == 1
    assert detect_yaml_version("examples/v2_minimal.yaml") == 2
    assert detect_yaml_version("examples/v2_ingest_demo.yaml") == 2


def test_documented_v2_persistence_filenames():
    cfg_path = Path("examples/v2_minimal.yaml")

    assert get_v2_presets_path(cfg_path).name == "v2_minimal.yaml.launchers.presets.json"
    assert get_v2_state_path(cfg_path).name == "v2_minimal.yaml.state.json"


def test_readme_contains_stable_doc_and_example_links():
    readme = Path("README.md").read_text(encoding="utf-8")

    for expected in [
        "docs/v2_spec.md",
        "docs/v1_to_v2_migration.md",
        "docs/v2_examples.md",
        "examples/yt_audio.yaml",
        "examples/v2_minimal.yaml",
        "examples/v2_ingest_demo.yaml",
    ]:
        assert expected in readme
