# pylint: disable=import-error
import importlib


MODULES = [
    "yaml_cli_ui.v2",
    "yaml_cli_ui.v2.models",
    "yaml_cli_ui.v2.loader",
    "yaml_cli_ui.v2.validator",
    "yaml_cli_ui.v2.expr",
    "yaml_cli_ui.v2.renderer",
    "yaml_cli_ui.v2.executor",
    "yaml_cli_ui.v2.errors",
    "yaml_cli_ui.v2.results",
]


def test_v2_modules_importable():
    for module_name in MODULES:
        assert importlib.import_module(module_name)


def test_v2_public_api_exports():
    from yaml_cli_ui.v2 import V2Document, load_v2_document, validate_v2_document

    assert V2Document is not None
    assert callable(load_v2_document)
    assert callable(validate_v2_document)
