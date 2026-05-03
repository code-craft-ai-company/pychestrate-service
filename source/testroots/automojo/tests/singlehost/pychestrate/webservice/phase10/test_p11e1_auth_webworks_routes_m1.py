"""
.. module:: test_p11e1_auth_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native auth REST routes.

.. moduleauthor:: Automation Mojo LLC

The auth port is the smallest of the M1 batch. Single route at
M1: ``POST /api/v1/auth/logout``. Tests cover the route matrix,
the 503 misconfig path, the 400 paths for malformed body and
missing session_id, and the happy 200 path including
session_service propagation.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from automojo.pychestrate.webservice.security.auth import (
    session_service as session_service_module,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (
    auth_routes,
)


class _FakeRequest:
    """
        Minimal duck-typed Request for the auth handlers.
    """

    def __init__(
        self,
        *,
        path: str,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.path_params: Dict[str, Any] = {}
        return

    def json(self) -> Any:
        if self._body_raises:
            raise ValueError("malformed json")
        return self._body


class _FakeApp:
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


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_auth_routes_attaches_logout_route():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: register_auth_routes attaches one route -- POST
    /api/v1/auth/logout -- matching the flask_restx controller.**
    """
    app = _FakeApp()
    auth_routes.register_auth_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/auth/logout", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# Misconfig + bad-body paths
# ---------------------------------------------------------------------------


def test_handle_logout_returns_503_when_session_missing():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: A request with no db_session attached produces the
    same 503 problem document the flask controller emitted.**
    """
    request = _FakeRequest(
        path="/api/v1/auth/logout",
        body={"session_id": "sess-x"},
        db_session=None,
    )
    response = auth_routes.handle_logout(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_logout_returns_400_when_body_is_not_json():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: An undecodable request body returns 400 problem+json.**
    """
    request = _FakeRequest(
        path="/api/v1/auth/logout",
        body_raises=True,
        db_session=object(),
    )
    response = auth_routes.handle_logout(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_handle_logout_returns_400_when_session_id_missing():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: A payload without ``session_id`` returns 400
    problem+json. Session_service.close_session must never be called
    with an empty session_id.**
    """
    close_patch = create_module_patch(
        session_service_module, "close_session"
    )
    try:
        mock_close = close_patch.activate()
        mock_close.configure(return_value=None)
        request = _FakeRequest(
            path="/api/v1/auth/logout",
            body={},
            db_session=object(),
        )
        response = auth_routes.handle_logout(request)
        testbase.assert_equal(response.status_code, 400)
        testbase.assert_equal(mock_close.call_count, 0)
    finally:
        close_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_handle_logout_invokes_session_service_and_returns_closed_status():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: A valid request invokes session_service.close_session
    with the supplied session_id and returns 200 with
    ``{session_id, status: closed}``.**
    """
    close_patch = create_module_patch(
        session_service_module, "close_session"
    )
    try:
        mock_close = close_patch.activate()
        mock_close.configure(return_value=None)
        request = _FakeRequest(
            path="/api/v1/auth/logout",
            body={"session_id": "sess-abc"},
            db_session=object(),
        )
        response = auth_routes.handle_logout(request)

        testbase.assert_equal(response.status_code, 200)
        body = _decode_body(response)
        testbase.assert_equal(body["session_id"], "sess-abc")
        testbase.assert_equal(body["status"], "closed")
        positional_args, keyword_args = mock_close.call_args_list[0]
        testbase.assert_equal(keyword_args["session_id"], "sess-abc")
    finally:
        close_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_auth_routes_and_calls_it():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_auth_routes
    into register_service_extensions.**
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from automojo.pychestrate.webservice.security.auth.restapi.v1.auth_routes import"
        in text
    )
    has_call = "register_auth_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


# ---------------------------------------------------------------------------
# Wire-shape sweep
# ---------------------------------------------------------------------------


def test_every_error_response_is_application_problem_json():
    """
    **Feature: 1-authentication T1.1 (webworks routes)**
    **Property: All error responses carry application/problem+json
    and are real JSONResponse instances.**
    """
    cases: List[Any] = []

    cases.append(auth_routes.handle_logout(
        _FakeRequest(path="/api/v1/auth/logout", body={}, db_session=None)
    ))
    cases.append(auth_routes.handle_logout(
        _FakeRequest(
            path="/api/v1/auth/logout",
            body_raises=True,
            db_session=object(),
        )
    ))
    cases.append(auth_routes.handle_logout(
        _FakeRequest(
            path="/api/v1/auth/logout", body={}, db_session=object()
        )
    ))

    for response in cases:
        testbase.assert_equal(
            response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
        )
        testbase.assert_equal(isinstance(response, JSONResponse), True)
    return
