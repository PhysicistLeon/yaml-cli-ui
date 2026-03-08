# pylint: disable=import-error

from pathlib import Path

import pytest

from yaml_cli_ui.v2.errors import V2LoadError
from yaml_cli_ui.v2.loader import load_v2_document


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_minimal_valid_root_v2_yaml(tmp_path: Path):
    root = tmp_path / "root.yaml"
    _write(
        root,
        """
version: 2
commands:
  hello_command:
    run:
      program: python
      argv: [-V]
launchers:
  hello:
    title: Hello
    use: hello_command
""",
    )

    doc = load_v2_document(root)

    assert doc.version == 2
    assert "hello_command" in doc.commands
    assert "hello" in doc.launchers


def test_root_source_path_and_base_dir_are_populated(tmp_path: Path):
    root = tmp_path / "x" / "root.yaml"
    _write(
        root,
        """
version: 2
commands:
  c:
    run:
      program: python
      argv: [-V]
launchers:
  l:
    title: L
    use: c
""",
    )

    doc = load_v2_document(root)

    assert doc.source_path == root.resolve()
    assert doc.base_dir == root.resolve().parent


def test_single_import_is_loaded(tmp_path: Path):
    imported = tmp_path / "packs" / "media.yaml"
    root = tmp_path / "root.yaml"
    _write(
        imported,
        """
version: 2
commands:
  shared_command:
    run:
      program: python
      argv: [-V]
""",
    )
    _write(
        root,
        """
version: 2
imports:
  media: ./packs/media.yaml
commands:
  hello_command:
    run:
      program: python
      argv: [-V]
launchers:
  hello:
    title: Hello
    use: hello_command
""",
    )

    doc = load_v2_document(root)

    assert "media" in doc.imported_documents
    assert "shared_command" in doc.imported_documents["media"].commands


def test_nested_imports_are_loaded(tmp_path: Path):
    leaf = tmp_path / "packs" / "leaf.yaml"
    mid = tmp_path / "packs" / "mid.yaml"
    root = tmp_path / "root.yaml"
    _write(
        leaf,
        """
version: 2
commands:
  leaf_command:
    run:
      program: python
      argv: [-V]
""",
    )
    _write(
        mid,
        """
version: 2
imports:
  leaf: ./leaf.yaml
pipelines:
  p:
    steps: [leaf_command]
""",
    )
    _write(
        root,
        """
version: 2
imports:
  mid: ./packs/mid.yaml
commands:
  root_command:
    run:
      program: python
      argv: [-V]
launchers:
  root:
    title: Root
    use: root_command
""",
    )

    doc = load_v2_document(root)

    assert "leaf" in doc.imported_documents["mid"].imported_documents


def test_import_cycle_raises_v2_load_error(tmp_path: Path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    _write(a, "version: 2\nimports: {b: ./b.yaml}\n")
    _write(b, "version: 2\nimports: {a: ./a.yaml}\n")

    with pytest.raises(V2LoadError, match="cycle"):
        load_v2_document(a)


def test_missing_import_file_raises_v2_load_error(tmp_path: Path):
    root = tmp_path / "root.yaml"
    _write(
        root,
        """
version: 2
imports:
  nope: ./missing.yaml
commands:
  c:
    run:
      program: python
      argv: [-V]
launchers:
  l:
    title: L
    use: c
""",
    )

    with pytest.raises(V2LoadError, match="does not exist"):
        load_v2_document(root)


def test_import_path_resolves_relative_to_source_file(tmp_path: Path):
    root = tmp_path / "root.yaml"
    folder = tmp_path / "sub" / "folder"
    imported = folder / "child.yaml"
    _write(
        imported,
        """
version: 2
commands:
  child:
    run:
      program: python
      argv: [-V]
""",
    )
    _write(
        root,
        """
version: 2
imports:
  rel: ./sub/folder/child.yaml
commands:
  c:
    run:
      program: python
      argv: [-V]
launchers:
  l:
    title: L
    use: c
""",
    )

    doc = load_v2_document(root)

    assert doc.imported_documents["rel"].source_path == imported.resolve()


def test_nested_import_path_resolves_relative_to_imported_file(tmp_path: Path):
    root = tmp_path / "root.yaml"
    imported = tmp_path / "packs" / "imported.yaml"
    shared = tmp_path / "packs" / "lib" / "shared.yaml"

    _write(
        shared,
        """
version: 2
commands:
  shared_command:
    run:
      program: python
      argv: [-V]
""",
    )
    _write(
        imported,
        """
version: 2
imports:
  shared: ./lib/shared.yaml
pipelines:
  p:
    steps: [shared_command]
""",
    )
    _write(
        root,
        """
version: 2
imports:
  imp: ./packs/imported.yaml
commands:
  c:
    run:
      program: python
      argv: [-V]
launchers:
  l:
    title: L
    use: c
""",
    )

    doc = load_v2_document(root)

    nested = doc.imported_documents["imp"].imported_documents["shared"]
    assert nested.source_path == shared.resolve()


def test_unknown_param_type_raises_v2_load_error(tmp_path: Path):
    root = tmp_path / "root.yaml"
    _write(
        root,
        """
version: 2
params:
  bad:
    type: unexpected_type
commands:
  c:
    run:
      program: python
      argv: [-V]
launchers:
  l:
    title: L
    use: c
""",
    )

    with pytest.raises(V2LoadError, match="unknown param type"):
        load_v2_document(root)
