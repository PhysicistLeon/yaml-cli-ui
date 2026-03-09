import pytest

from tests.v2_test_utils import fixture_path
from yaml_cli_ui.v2.errors import V2ValidationError
from yaml_cli_ui.v2.loader import load_v2_document


def test_invalid_future_local_fixture_fails_validation():
    with pytest.raises(V2ValidationError, match="V2E_LOCALS_ORDERING"):
        load_v2_document(fixture_path("invalid_future_local.yaml"))


def test_callable_name_collision_fixture_fails_validation():
    with pytest.raises(V2ValidationError, match="V2E_CALLABLE_NAMESPACE_CONFLICT"):
        load_v2_document(fixture_path("invalid_callable_collision.yaml"))


def test_invalid_imported_doc_with_launchers_fails_validation():
    with pytest.raises(V2ValidationError, match="V2E_IMPORTED_LAUNCHERS_FORBIDDEN"):
        load_v2_document(fixture_path("invalid_imported_with_launchers_root.yaml"))
