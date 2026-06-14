"""
.. module:: test_p11e1_auth_logout_authz_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Session-ownership enforcement tests for POST /api/v1/auth/logout.

.. moduleauthor:: Code Craft AI LLC

Closes the gap identified in the REST-auth-hardening audit (hole #4).

``handle_logout`` previously accepted any caller-supplied ``session_id``
without verifying ownership. It now:

1. Requires an authenticated caller (``auth_principal`` present).
2. Rejects with 403 a ``session_id`` that does not match the caller's
   own ``session_id``.
3. Accepts and closes ``session_id`` when it matches the caller's own
   session.

Tests:

* 401 — no auth_principal.
* 403 — session_id belongs to a different session than the caller owns.
* 200 — caller closes their own session.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.security.auth import (
    session_service as session_service_module,
)
from ccai.pychestrate.webservice.security.auth.restapi.v1 import auth_routes


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakePrincipal:
    def __init__(
        self,
        *,
        user_id: str = "caller-1",
        session_id: str = "my-sess-1",
    ) -> None:
        self.user_id: str = user_id
        self.session_id: str = session_id
        return


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        body: Any = None,
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.path_params: Dict[str, Any] = {}
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        return self._body


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


# ---------------------------------------------------------------------------
# 401 — unauthenticated
# ---------------------------------------------------------------------------


def test_logout_returns_401_when_principal_absent():
    """
    **Feature: rest-auth-hardening hole #4**
    **Property: POST /api/v1/auth/logout returns 401 when no
    auth_principal is attached to the request.**
    """
    request = _FakeRequest(
        path="/api/v1/auth/logout",
        body={"session_id": "some-sess"},
        db_session=object(),
        auth_principal=None,
    )
    response = auth_routes.handle_logout(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


# ---------------------------------------------------------------------------
# 403 — ownership violation
# ---------------------------------------------------------------------------


def test_logout_returns_403_when_session_id_belongs_to_other_user():
    """
    **Feature: rest-auth-hardening hole #4**
    **Property: A caller cannot close another user's session.
    The session_id in the body (``other-sess``) differs from the
    caller's session_id (``my-sess``); the handler must return 403
    without calling close_session.**
    """
    close_patch = create_module_patch(
        session_service_module, "close_session"
    )
    try:
        mock_close = close_patch.activate()
        mock_close.configure(return_value=None)

        caller = _FakePrincipal(session_id="my-sess")
        request = _FakeRequest(
            path="/api/v1/auth/logout",
            body={"session_id": "other-sess"},
            db_session=object(),
            auth_principal=caller,
        )
        response = auth_routes.handle_logout(request)

        testbase.assert_equal(response.status_code, 403)
        body = _decode_body(response)
        testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
        # close_session must NOT have been called
        testbase.assert_equal(mock_close.call_count, 0)
    finally:
        close_patch.deactivate()
    return


def test_logout_returns_403_for_any_foreign_session_regardless_of_user_id():
    """
    **Feature: rest-auth-hardening hole #4**
    **Property: Even if the caller knows the session_id of another
    session on the same account (edge case), ownership is compared
    by session_id only. A mismatched session_id always yields 403.**
    """
    close_patch = create_module_patch(
        session_service_module, "close_session"
    )
    try:
        mock_close = close_patch.activate()
        mock_close.configure(return_value=None)

        caller = _FakePrincipal(
            user_id="shared-user", session_id="sess-a"
        )
        request = _FakeRequest(
            path="/api/v1/auth/logout",
            body={"session_id": "sess-b"},
            db_session=object(),
            auth_principal=caller,
        )
        response = auth_routes.handle_logout(request)

        testbase.assert_equal(response.status_code, 403)
        testbase.assert_equal(mock_close.call_count, 0)
    finally:
        close_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# 200 — happy path (own session)
# ---------------------------------------------------------------------------


def test_logout_succeeds_when_caller_closes_own_session():
    """
    **Feature: rest-auth-hardening hole #4**
    **Property: A caller may close their own session.
    The session_id in the body matches the caller's session_id;
    session_service.close_session is called once, and the response
    is 200 with ``{session_id, status: closed}``.**
    """
    close_patch = create_module_patch(
        session_service_module, "close_session"
    )
    try:
        mock_close = close_patch.activate()
        mock_close.configure(return_value=None)

        own_session_id = "sess-mine"
        caller = _FakePrincipal(session_id=own_session_id)
        request = _FakeRequest(
            path="/api/v1/auth/logout",
            body={"session_id": own_session_id},
            db_session=object(),
            auth_principal=caller,
        )
        response = auth_routes.handle_logout(request)

        testbase.assert_equal(response.status_code, 200)
        body = _decode_body(response)
        testbase.assert_equal(body["session_id"], own_session_id)
        testbase.assert_equal(body["status"], "closed")
        testbase.assert_equal(mock_close.call_count, 1)
        _positional_args, keyword_args = mock_close.call_args_list[0]
        testbase.assert_equal(keyword_args["session_id"], own_session_id)
    finally:
        close_patch.deactivate()
    return
