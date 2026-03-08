# pylint: disable=import-error
import pytest

from yaml_cli_ui.v2.errors import V2ValidationError
from yaml_cli_ui.v2.models import V2Document
from yaml_cli_ui.v2.validator import validate_v2_document


def make_doc(raw):
    return V2Document(raw=raw, version=raw.get("version", 0))


def test_validate_v2_document_accepts_minimal_valid_doc():
    raw = {
        "version": 2,
        "launchers": {
            "hello": {
                "title": "Hello",
                "use": "hello_command",
            }
        },
        "commands": {
            "hello_command": {
                "run": {
                    "program": "python",
                    "argv": ["-V"],
                }
            }
        },
    }

    validate_v2_document(make_doc(raw))


def test_validate_v2_document_rejects_wrong_version():
    with pytest.raises(V2ValidationError, match="expected 2"):
        validate_v2_document(make_doc({"version": 1, "launchers": {"x": {}}}))


def test_validate_v2_document_rejects_missing_launchers():
    with pytest.raises(V2ValidationError, match="launchers"):
        validate_v2_document(make_doc({"version": 2}))
