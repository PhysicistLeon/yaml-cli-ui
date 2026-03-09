import pytest

from tests.v2_test_utils import fixture_path
from yaml_cli_ui.v2.errors import V2LoadError
from yaml_cli_ui.v2.loader import load_v2_document


def test_minimal_root_loads_with_source_and_base_dir():
    doc = load_v2_document(fixture_path("minimal_root.yaml"))

    assert doc.version == 2
    assert doc.launchers
    assert doc.source_path == fixture_path("minimal_root.yaml").resolve()
    assert doc.base_dir == fixture_path("minimal_root.yaml").resolve().parent


def test_with_imports_loads_recursively_and_relative_paths():
    doc = load_v2_document(fixture_path("with_imports_root.yaml"))

    assert set(doc.imported_documents.keys()) == {"media", "fs"}
    assert "fs" in doc.imported_documents["media"].imported_documents
    assert doc.imported_documents["media"].source_path == fixture_path("packs/media.yaml").resolve()


def test_missing_import_file_raises_v2_load_error():
    with pytest.raises(V2LoadError, match="does not exist"):
        load_v2_document(fixture_path("invalid_missing_import_root.yaml"))


def test_import_cycle_raises_v2_load_error():
    with pytest.raises(V2LoadError, match="import cycle"):
        load_v2_document(fixture_path("invalid_import_cycle_root.yaml"))
