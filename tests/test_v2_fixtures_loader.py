from pathlib import Path

from tests.v2_test_utils import fixture_path
from yaml_cli_ui.v2.loader import load_v2_document


def test_minimal_root_fixture_loads_with_metadata():
    fixture = fixture_path("minimal_root.yaml")

    doc = load_v2_document(fixture)

    assert doc.version == 2
    assert doc.launchers
    assert doc.source_path == fixture.resolve()
    assert doc.base_dir == fixture.resolve().parent


def test_with_imports_resolves_recursive_docs_and_relative_paths():
    doc = load_v2_document(fixture_path("with_imports_root.yaml"))

    assert "media" in doc.imported_documents
    assert "fs" in doc.imported_documents
    media_doc = doc.imported_documents["media"]
    assert media_doc.source_path == fixture_path("packs/media.yaml").resolve()
    assert "fs" in media_doc.imported_documents
    assert media_doc.imported_documents["fs"].source_path == fixture_path("packs/fs.yaml").resolve()
