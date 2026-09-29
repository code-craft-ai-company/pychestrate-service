"""
.. module:: test_p31m_api_reference_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the REST reference page
               ``GET /api/v1/_meta/docs`` (DOC-06).

.. moduleauthor:: Code Craft AI LLC

None of the 16 URLs an evaluator would try for the API reference was
served, although the service already served the OpenAPI document and
codecraftai-webworks ships ReDoc. ``GET /api/docs`` now renders the
document with the bundled ReDoc, served from this origin so the page
works under the service's Content-Security-Policy, to any signed-in
caller. It lives under ``/api/v1/`` because only that prefix resolves
the session cookie; ``GET /api/docs`` redirects to it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.api import openapi_document
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal

from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
)


class _FakeRequest:
    def __init__(self, *, path: str, auth_principal: Optional[Any], path_params: Optional[Dict[str, str]] = None) -> None:
        self.path = path
        self.auth_principal = auth_principal
        self.path_params = path_params if path_params is not None else {}
        self.db_session = None
        return


def _principal() -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id="u-1", session_id="s-1", provider_kind=AuthProviderKind.LOCAL, provider_name="local",
    )
    return rtnval


PAGE_PATH: str = "/api/v1/_meta/docs"
ASSET_PATTERN: str = "/api/v1/_meta/docs/assets/{filename}"


def _app() -> Any:
    app = make_fake_app()
    openapi_document.register_api_docs_routes(app=app, version_prefix="/api/v1")
    return app


def _page(*, principal: Optional[Any]) -> Any:
    handler = _app().find_handler(path=PAGE_PATH, method="GET")
    rtnval = handler(_FakeRequest(path=PAGE_PATH, auth_principal=principal))
    return rtnval


def _asset(*, filename: str, principal: Optional[Any]) -> Any:
    # The fake app records the route pattern, not a concrete path.
    handler = _app().find_handler(path=ASSET_PATTERN, method="GET")
    path = "/api/v1/_meta/docs/assets/{}".format(filename)
    rtnval = handler(_FakeRequest(path=path, auth_principal=principal, path_params={"filename": filename}))
    return rtnval


def test_the_reference_page_renders_redoc_from_the_served_document():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: GET /api/v1/_meta/docs answers 200 HTML that points
    ReDoc at /api/v1/_meta/openapi.json and loads its script from this
    origin.**
    """
    response = _page(principal=_principal())
    html = response.body.decode("utf-8")

    testbase.assert_equal(
        (response.status_code,
         'spec-url="/api/v1/_meta/openapi.json"' in html,
         'src="/api/v1/_meta/docs/assets/redoc.standalone.js"' in html,
         "http://" in html or "https://" in html),
        (200, True, True, False),
    )
    return


def test_the_reference_page_needs_a_signed_in_caller():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: an anonymous caller gets 401, as for the OpenAPI
    document the page renders.**
    """
    response = _page(principal=None)

    testbase.assert_equal(response.status_code, 401)
    return


def test_the_redoc_script_is_served_from_this_origin():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: the bundled ReDoc script is served as JavaScript and is
    the real library (hundreds of kilobytes).**
    """
    response = _asset(filename="redoc.standalone.js", principal=_principal())

    testbase.assert_equal(
        (response.status_code, response.headers.get("Content-Type", ""), len(response.body) > 500_000),
        (200, "application/javascript", True),
    )
    return


def test_only_the_redoc_script_is_served_as_an_asset():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: any other name, including one that climbs out of the
    asset directory, answers 404 and no file content.**
    """
    answers = []
    for name in ("manifest.json", "../manifest.json", "..%2fmanifest.json", "../../static/manifest.json", ""):
        response = _asset(filename=name, principal=_principal())
        answers.append((response.status_code, b"redoc" in response.body.lower() and len(response.body) > 10_000))

    testbase.assert_equal(answers, [(404, False)] * 5)
    return


def test_the_script_needs_a_signed_in_caller():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: an anonymous caller gets 401 for the script too.**
    """
    response = _asset(filename="redoc.standalone.js", principal=None)

    testbase.assert_equal(response.status_code, 401)
    return


def test_the_address_people_try_first_redirects_to_the_page():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: GET /api/docs, which is outside the prefix that
    resolves a session, answers a redirect to the reference page.**
    """
    handler = _app().find_handler(path="/api/docs", method="GET")
    response = handler(_FakeRequest(path="/api/docs", auth_principal=None))

    testbase.assert_equal(
        (response.status_code in (301, 302, 307, 308), response.headers.get("Location", "")),
        (True, PAGE_PATH),
    )
    return


def test_the_reference_page_allows_the_search_worker_and_nothing_third_party():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: the page sets its own policy that permits a blob:
    worker (ReDoc's search) and names no third-party host.**
    """
    response = _page(principal=_principal())
    policy = response.headers.get("Content-Security-Policy", "")

    testbase.assert_equal(("worker-src 'self' blob:" in policy, "http" in policy), (True, False))
    return


def test_the_served_document_names_the_right_licence():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: the OpenAPI document declares the Pychestrate End User
    License Agreement, not Apache-2.0.**
    """
    openapi_document.reset_cache_for_testing()
    document = openapi_document.load_served_document()

    testbase.assert_equal(
        (document["info"]["license"]["name"], "apache" in str(document["info"]["license"]).lower()),
        ("Pychestrate End User License Agreement", False),
    )
    return
