"""
.. module:: test_p26d_openapi_document_route_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ``GET /api/v1/_meta/openapi.json``.

.. moduleauthor:: Code Craft AI LLC

The ``pyc`` CLI builds its commands from the service's OpenAPI
document, but the service never served it (audit finding CLI-01: every
generated command failed with "OpenAPI document is not available ...
404"). :mod:`api.openapi_document` now serves
``specs/openapi/pychestrate.yaml`` as JSON to signed-in callers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import tempfile

from pathlib import Path
from typing import Any, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api import openapi_document
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal

from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
)


class _FakeRequest:
    def __init__(self, *, auth_principal: Optional[Any]) -> None:
        self.path = "/api/v1/_meta/openapi.json"
        self.auth_principal = auth_principal
        self.db_session = None
        return


def _principal() -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id="u-1", session_id="s-1", provider_kind=AuthProviderKind.LOCAL, provider_name="local",
    )
    return rtnval


def _registered_handler() -> Any:
    app = make_fake_app()
    openapi_document.register_openapi_document_routes(app=app, version_prefix="/api/v1")
    rtnval = app.find_handler(path="/api/v1/_meta/openapi.json", method="GET")
    return rtnval


def _body(response: Any) -> Any:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


def test_route_serves_the_contract_to_a_signed_in_caller():
    """
    **Feature: OpenAPI document route (CLI-01)**
    **Property: GET /api/v1/_meta/openapi.json answers 200 with the
    repository's OpenAPI document (its paths include /projects).**
    """
    openapi_document.reset_cache_for_testing()
    response = _registered_handler()(_FakeRequest(auth_principal=_principal()))
    document = _body(response)
    testbase.assert_equal(
        (response.status_code, document["openapi"].startswith("3."), "/projects" in document["paths"]),
        (200, True, True),
    )
    return


def test_served_document_points_servers_at_the_answering_host():
    """
    **Feature: OpenAPI document route (CLI-01)**
    **Property: the served document's servers list is /api/v1 (relative
    to the host that answered), not the author's deployment.**
    """
    openapi_document.reset_cache_for_testing()
    document = _body(_registered_handler()(_FakeRequest(auth_principal=_principal())))
    testbase.assert_equal([server["url"] for server in document["servers"]], ["/api/v1"])
    return


def test_served_document_describes_the_token_routes():
    """
    **Feature: OpenAPI document route (CLI-01 / ORG-F02)**
    **Property: the served contract includes /me/api-tokens, so pyc
    can generate the api-tokens commands.**
    """
    openapi_document.reset_cache_for_testing()
    document = _body(_registered_handler()(_FakeRequest(auth_principal=_principal())))
    testbase.assert_equal("post" in document["paths"]["/me/api-tokens"], True)
    return


def test_route_refuses_an_anonymous_caller():
    """
    **Feature: OpenAPI document route (CLI-01)**
    **Property: without a principal the route answers 401 (it is not
    on the anonymous allowlist).**
    """
    response = _registered_handler()(_FakeRequest(auth_principal=None))
    testbase.assert_equal(response.status_code, 401)
    return


def test_route_answers_404_when_the_deployment_has_no_spec():
    """
    **Feature: OpenAPI document route (CLI-01)**
    **Property: a deployment without specs/ answers a 404 problem
    document (pyc then falls back to its built-in commands).**
    """
    openapi_document.reset_cache_for_testing()
    patch = create_module_patch(openapi_document, "locate_spec_file")
    mock = patch.activate()
    mock.configure(return_value=None)
    try:
        response = openapi_document.handle_get_openapi_document(_FakeRequest(auth_principal=_principal()))
    finally:
        patch.deactivate()
        openapi_document.reset_cache_for_testing()
    testbase.assert_equal(
        (response.status_code, response.headers.get("Content-Type")), (404, "application/problem+json")
    )
    return


def test_spec_is_found_by_walking_up_from_a_directory():
    """
    **Feature: OpenAPI document route (CLI-01)**
    **Property: locate_spec_file finds specs/openapi/pychestrate.yaml in
    an ancestor directory.**
    """
    with tempfile.TemporaryDirectory() as root:
        spec = Path(root) / "specs" / "openapi" / "pychestrate.yaml"
        spec.parent.mkdir(parents=True)
        spec.write_text("openapi: 3.1.0\npaths: {}\n", encoding="utf-8")
        nested = Path(root) / "source" / "site" / "pkg"
        nested.mkdir(parents=True)
        testbase.assert_equal(openapi_document.locate_spec_file(start=nested), spec)
    return
