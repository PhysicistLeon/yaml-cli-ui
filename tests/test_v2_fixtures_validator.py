# pylint: disable=import-error

import pytest

from tests.v2_test_utils import fixture_path
from yaml_cli_ui.v2.errors import V2ValidationError
from yaml_cli_ui.v2.loader import resolve_imports
from yaml_cli_ui.v2.validator import validate_v2_document


def test_invalid_future_local_fails_validation():
    doc = resolve_imports(fixture_path("invalid_future_local.yaml"))

    with pytest.raises(V2ValidationError, match="V2E_LOCALS_ORDERING"):
        validate_v2_document(doc)


def test_conflicting_callable_names_fail_validation():
    doc = resolve_imports(fixture_path("invalid_callable_collision.yaml"))

    with pytest.raises(V2ValidationError, match="V2E_CALLABLE_NAMESPACE_CONFLICT"):
        validate_v2_document(doc)


def test_invalid_imported_doc_with_launchers_fails_validation():
    doc = resolve_imports(fixture_path("invalid_imported_with_launchers_root.yaml"))

    with pytest.raises(V2ValidationError, match="V2E_IMPORTED_LAUNCHERS_FORBIDDEN"):
        validate_v2_document(doc)


def test_invalid_imported_doc_with_profiles_fails_validation():
    doc = resolve_imports(fixture_path("invalid_imported_with_profiles_root.yaml"))

    with pytest.raises(V2ValidationError, match="V2E_IMPORTED_PROFILES_FORBIDDEN"):
        validate_v2_document(doc)
