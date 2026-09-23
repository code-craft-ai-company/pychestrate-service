"""
.. module:: test_p21b_embed_plugin_api_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the embeddable-views REST surface + the
               hardened plugin-api meta routes.

.. moduleauthor:: Code Craft AI LLC

Covers ``8-embeddable-views`` PR p21b:

* ``GET /api/v1/embed/views`` lists the fixed catalog and is
  RBAC-gated on ``system:embed.read``.
* ``POST /api/v1/embed/views/{view_key}:sign`` mints a signed URL,
  is RBAC-gated on ``system:embed.sign``, and 404s an unknown view.
* ``GET /embed/{view_key}`` (token-auth, chromeless) serves the
  embed HTML for a valid token, 401s a missing / malformed token,
  403s a tampered / expired token, 404s an unknown view kind.

and the plugin-api hardening:

* the plugin-api meta routes (``catalog``) and the new
  ``GET /api/v1/ext`` listing are RBAC-gated on
  ``system:plugin_api.read`` (401 anonymous, 403 denied).

RBAC is exercised by stubbing ``rbac_evaluator.check_permission``;
the embed serving route is framework-free token verification so the
tests round-trip a real signed URL through ``key_provider``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import time

from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.embed import key_provider
from ccai.pychestrate.webservice.embed.restapi.v1 import embed_routes
from ccai.pychestrate.webservice.embed.signing import issue_signed_url
from ccai.pychestrate.webservice.plugin_api.restapi.v1 import catalog_routes
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    """
        Minimal duck-typed query-params map.
    """

    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakePrincipal:
    """
        Stand-in for an AuthPrincipal.
    """

    def __init__(
        self, *, user_id: str = "u-1", email: str = "op@example.com"
    ) -> None:
        self.user_id: str = user_id
        self.email: str = email
        return


class _FakeRequest:
    """
        Minimal duck-typed webworks Request.
    """

    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        if self._body_raises is True:
            raise ValueError("malformed json")
        rtnval = self._body
        return rtnval


class _FakeApp:
    """
        Records ``attach_route`` calls.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


class _FakeDecision:
    """
        Stand-in for :class:`AuthzDecision`.
    """

    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        return


def _decode_body(response: Any) -> Any:
    """
        Decode a response body as JSON.

        :param response: webworks response.

        :returns: Parsed JSON.
    """
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_permission(*, allowed: bool) -> Any:
    """
        Patch ``rbac_evaluator.check_permission`` to return a fixed
        decision.

        :param allowed: The decision the stub returns.

        :returns: The active module patch (call ``deactivate()``).
    """
    patch = create_module_patch(rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(return_value=_FakeDecision(allowed=allowed))
    rtnval = patch
    return rtnval


def _sign_and_query(*, view_key: str, resource_id: str) -> Dict[str, str]:
    """
        Mint a signed URL through the process key provider and return
        the query-string params for the serving route.

        :param view_key: View kind name.
        :param resource_id: Resource id to bind.

        :returns: Dict of serving-route query params.
    """
    key_provider.reset_for_testing()
    signing_key = key_provider.get_active_signing_key()
    # The serving route checks the token against real wall-clock time,
    # so the issued expiry must be in the real future.
    signed = issue_signed_url(
        view_kind=view_key,
        resource_id=resource_id,
        audience="op@example.com",
        ttl_seconds=3600,
        signing_key=signing_key,
        now_unix=int(time.time()),
    )
    parsed = parse_qs(urlparse(signed.url).query)
    rtnval = {
        "resource_id": resource_id,
        "a": parsed["a"][0],
        "e": parsed["e"][0],
        "k": parsed["k"][0],
        "s": parsed["s"][0],
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/embed/views
# ---------------------------------------------------------------------------


def test_list_views_authorized_returns_catalog():
    """
        An authorized caller gets the five-entry catalog.
    """
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_list_views(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["total"], 5)
    view_kinds = [entry["view_kind"] for entry in body["items"]]
    testbase.assert_true("run_detail" in view_kinds)
    testbase.assert_true("project_dashboard_tile" in view_kinds)
    return


def test_list_views_anonymous_is_401():
    """
        A request with no principal is rejected 401.
    """
    request = _FakeRequest(
        path="/api/v1/embed/views",
        db_session=object(),
        auth_principal=None,
    )
    response = embed_routes.handle_list_views(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_list_views_denied_is_403():
    """
        A principal lacking ``system:embed.read`` gets 403.
    """
    patch = _patch_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_list_views(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


# ---------------------------------------------------------------------------
# POST /api/v1/embed/views/{view_key}:sign
# ---------------------------------------------------------------------------


def test_sign_returns_signed_url():
    """
        Signing a known view kind returns a signed URL + snippets.
    """
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views/run_detail:sign",
            path_params={"view_key": "run_detail"},
            body={"resource_id": "run-42", "ttl_seconds": 600},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_sign_view(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_true(body["url"].startswith("/embed/run_detail/run-42"))
    testbase.assert_equal(body["view_kind"], "run_detail")
    testbase.assert_equal(body["ttl_seconds"], 600)
    testbase.assert_true("iframe_snippet" in body)
    testbase.assert_true("webcomponent_snippet" in body)
    return


def test_sign_unknown_view_is_404():
    """
        An unknown view key is rejected 404.
    """
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views/nope:sign",
            path_params={"view_key": "nope"},
            body={},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_sign_view(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_sign_ttl_exceeded_is_400():
    """
        A ttl_seconds above the ceiling is rejected 400.
    """
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views/run_detail:sign",
            path_params={"view_key": "run_detail"},
            body={"ttl_seconds": 999999},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_sign_view(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_sign_denied_is_403():
    """
        A principal lacking ``system:embed.sign`` gets 403.
    """
    patch = _patch_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views/run_detail:sign",
            path_params={"view_key": "run_detail"},
            body={},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_sign_view(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


def test_sign_bad_ttl_type_is_422():
    """
        A non-integer ttl_seconds is rejected 422.
    """
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/embed/views/run_detail:sign",
            path_params={"view_key": "run_detail"},
            body={"ttl_seconds": "soon"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = embed_routes.handle_sign_view(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


# ---------------------------------------------------------------------------
# GET /embed/{view_key}  (token-auth serving route)
# ---------------------------------------------------------------------------


def test_serve_valid_token_renders_html():
    """
        A valid token renders the WebComponent HTML document.
    """
    query = _sign_and_query(view_key="run_detail", resource_id="run-7")
    request = _FakeRequest(
        path="/embed/run_detail",
        path_params={"view_key": "run_detail"},
        query=query,
    )
    response = embed_routes.handle_serve_embed(request)
    testbase.assert_equal(response.status_code, 200)
    html = response.body.decode("utf-8")
    testbase.assert_true("pyc-run-detail" in html)
    testbase.assert_true("run-7" in html)
    return


def test_serve_missing_token_is_401():
    """
        No token query params -> 401 (malformed payload).
    """
    request = _FakeRequest(
        path="/embed/run_detail",
        path_params={"view_key": "run_detail"},
        query={},
    )
    response = embed_routes.handle_serve_embed(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_serve_tampered_token_is_403():
    """
        A tampered signature -> 403 (signature mismatch).
    """
    query = _sign_and_query(view_key="run_detail", resource_id="run-7")
    query["s"] = "0" * len(query["s"])
    request = _FakeRequest(
        path="/embed/run_detail",
        path_params={"view_key": "run_detail"},
        query=query,
    )
    response = embed_routes.handle_serve_embed(request)
    testbase.assert_equal(response.status_code, 403)
    return


def test_serve_expired_token_is_403():
    """
        An expired token -> 403.
    """
    key_provider.reset_for_testing()
    signing_key = key_provider.get_active_signing_key()
    signed = issue_signed_url(
        view_kind="run_detail",
        resource_id="run-7",
        audience="op@example.com",
        ttl_seconds=1,
        signing_key=signing_key,
        now_unix=10,
    )
    parsed = parse_qs(urlparse(signed.url).query)
    query = {
        "resource_id": "run-7",
        "a": parsed["a"][0],
        "e": parsed["e"][0],
        "k": parsed["k"][0],
        "s": parsed["s"][0],
    }
    request = _FakeRequest(
        path="/embed/run_detail",
        path_params={"view_key": "run_detail"},
        query=query,
    )
    response = embed_routes.handle_serve_embed(request)
    testbase.assert_equal(response.status_code, 403)
    return


def test_serve_unknown_view_is_404():
    """
        An unknown view kind -> 404.
    """
    request = _FakeRequest(
        path="/embed/nope",
        path_params={"view_key": "nope"},
        query={},
    )
    response = embed_routes.handle_serve_embed(request)
    testbase.assert_equal(response.status_code, 404)
    return


def test_register_attaches_three_embed_routes():
    """
        Registration attaches the two API routes plus the top-level
        serving route.
    """
    app = _FakeApp()
    embed_routes.register_embed_routes(app=app, version_prefix="/api/v1")
    paths = [call[0] for call in app.calls]
    testbase.assert_true("/api/v1/embed/views" in paths)
    testbase.assert_true("/api/v1/embed/views/{view_key}:sign" in paths)
    testbase.assert_true("/embed/{view_key}" in paths)
    return


# ---------------------------------------------------------------------------
# plugin-api hardening
# ---------------------------------------------------------------------------


def test_plugin_api_catalog_anonymous_is_401():
    """
        The catalog route rejects an anonymous caller 401.
    """
    request = _FakeRequest(
        path="/api/v1/plugin-api/_meta/catalog",
        db_session=object(),
        auth_principal=None,
    )
    response = catalog_routes.handle_list_catalog(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_plugin_api_catalog_denied_is_403():
    """
        The catalog route rejects a denied caller 403.
    """
    patch = _patch_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/plugin-api/_meta/catalog",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = catalog_routes.handle_list_catalog(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


def test_list_ext_authorized_returns_listing():
    """
        ``GET /api/v1/ext`` returns the discovered-endpoint listing
        for an authorized caller; before any app has mounted the
        routes it reports ``dynamic_mount: deferred``.
    """
    from ccai.pychestrate.webservice.plugin_api.restapi.v1 import ext_mount_routes  # noqa: E402
    ext_mount_routes.reset_extension_mounts_for_testing()
    patch = _patch_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/ext",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = catalog_routes.handle_list_ext(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_true("items" in body)
    testbase.assert_true("total" in body)
    testbase.assert_equal(body["dynamic_mount"], "deferred")
    return


def test_list_ext_anonymous_is_401():
    """
        ``GET /api/v1/ext`` rejects an anonymous caller 401.
    """
    request = _FakeRequest(
        path="/api/v1/ext",
        db_session=object(),
        auth_principal=None,
    )
    response = catalog_routes.handle_list_ext(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_register_catalog_routes_attaches_ext_listing():
    """
        Registration attaches the ``/api/v1/ext`` listing route.
    """
    app = _FakeApp()
    catalog_routes.register_catalog_routes(app=app, version_prefix="/api/v1")
    paths = [call[0] for call in app.calls]
    testbase.assert_true("/api/v1/ext" in paths)
    return
