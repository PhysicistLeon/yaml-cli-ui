# pylint: disable=import-error

from pathlib import Path
import textwrap

import pytest

from yaml_cli_ui.v2.errors import V2LoadError
from yaml_cli_ui.v2.loader import load_v2_document


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


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


def test_root_source_path_and_base_dir_are_set(tmp_path: Path):
    root = tmp_path / "root.yaml"
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
            title: T
            use: c
        """,
    )

    doc = load_v2_document(root)

    assert doc.source_path == root.resolve()
    assert doc.base_dir == root.resolve().parent


def test_single_import_loads_document(tmp_path: Path):
    imported = tmp_path / "packs" / "shared.yaml"
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
          shared: ./packs/shared.yaml
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

    assert "shared" in doc.imported_documents
    assert "shared_command" in doc.imported_documents["shared"].commands


def test_nested_imports_load_recursively(tmp_path: Path):
    leaf = tmp_path / "packs" / "leaf.yaml"
    middle = tmp_path / "packs" / "middle.yaml"
    root = tmp_path / "root.yaml"
    _write(
        leaf,
        """
        version: 2
        pipelines:
          leaf_pipe:
            steps: [x]
        """,
    )
    _write(
        middle,
        """
        version: 2
        imports:
          leaf: ./leaf.yaml
        commands:
          mid_cmd:
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
          mid: ./packs/middle.yaml
        commands:
          root_cmd:
            run:
              program: python
              argv: [-V]
        launchers:
          root:
            title: Root
            use: root_cmd
        """,
    )

    doc = load_v2_document(root)

    assert "mid" in doc.imported_documents
    assert "leaf" in doc.imported_documents["mid"].imported_documents


def test_import_cycle_raises_load_error(tmp_path: Path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    _write(a, "version: 2\nimports: {b: ./b.yaml}\n")
    _write(b, "version: 2\nimports: {a: ./a.yaml}\n")

    with pytest.raises(V2LoadError, match="cycle"):
        load_v2_document(a)


def test_missing_import_file_raises_load_error(tmp_path: Path):
    root = tmp_path / "root.yaml"
    _write(
        root,
        """
        version: 2
        imports:
          x: ./missing.yaml
        commands:
          c:
            run:
              program: python
              argv: [-V]
        launchers:
          l:
            title: T
            use: c
        """,
    )

    with pytest.raises(V2LoadError, match="missing file"):
        load_v2_document(root)


def test_import_path_is_resolved_relative_to_source_file(tmp_path: Path):
    shared = tmp_path / "packs" / "lib" / "shared.yaml"
    root = tmp_path / "root.yaml"
    imported = tmp_path / "packs" / "imported.yaml"
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
        commands:
          imp_cmd:
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
          imp: ./packs/imported.yaml
        commands:
          root_cmd:
            run:
              program: python
              argv: [-V]
        launchers:
          root:
            title: Root
            use: root_cmd
        """,
    )

    doc = load_v2_document(root)
    nested = doc.imported_documents["imp"].imported_documents["shared"]

    assert nested.source_path == shared.resolve()
