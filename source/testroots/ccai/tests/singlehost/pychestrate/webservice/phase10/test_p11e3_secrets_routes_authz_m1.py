"""
.. module:: test_p11e3_secrets_routes_authz_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Authorization-gate tests for the secrets metadata routes.

.. moduleauthor:: Code Craft AI LLC

Closes the gaps identified in the REST-auth-hardening audit (hole #5).

Both ``GET /api/v1/secrets`` and ``GET /api/v1/secrets/{secret_ref}``
previously returned data with no auth gate. They now require:

1. An authenticated caller (``auth_principal`` present → 401 if absent).
2. The caller to hold ``system:secrets.read`` (or ``.admin``, evaluated
   by the RBAC evaluator → 403 if denied).

Tests cover:

* ``GET /api/v1/secrets`` → 401 / 403 / 200.
* ``GET /api/v1/secrets/{secret_ref}`` → 401 / 403 / 200.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.secrets.restapi.v1 import secrets_routes


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakePrincipal:
    def __init__(self, *, user_id: str = "caller-1") -> None:
        self.user_id: str = user_id
        self.session_id: str = "sess-caller-1"
        return


class _FakeScopeKind:
    def __init__(self, value: str = "ORG") -> None:
        self.value: str = value
        return


class _FakeRecord:
    def __init__(self, *, secret_ref: str) -> None:
        self.secret_ref: str = secret_ref
        self.backend_name: str = "local-db"
        self.scope_kind: _FakeScopeKind = _FakeScopeKind("ORG")
        self.scope_ref: Optional[str] = None
        self.current_version_id: Optional[str] = None
        self.created_at: datetime = datetime(
            2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeQuery:
    def __init__(
        self,
        *,
        rows: Optional[List[_FakeRecord]] = None,
        first_value: Optional[_FakeRecord] = None,
    ) -> None:
        self._rows: List[_FakeRecord] = rows if rows is not None else []
        self._first_value: Optional[_FakeRecord] = first_value
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def all(self) -> List[_FakeRecord]:
        return list(self._rows)

    def first(self) -> Optional[_FakeRecord]:
        return self._first_value


class _FakeDbSession:
    def __init__(
        self,
        *,
        rows: Optional[List[_FakeRecord]] = None,
        first_value: Optional[_FakeRecord] = None,
    ) -> None:
        self._query: _FakeQuery = _FakeQuery(
            rows=rows, first_value=first_value
        )
        return

    def query(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self._query


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        self.reason: str = "allow" if allowed else "no binding"
        self.permission_key: str = "system:secrets.read"
        return


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: Dict[str, Any] = (
            query_params if query_params is not None else {}
        )
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_evaluator(*, allowed: bool) -> Any:
    """
        Patch ``secrets_routes.rbac_evaluator.check_permission`` to return
        an allowed or denied decision.

        :param allowed: Whether the check should allow.

        :returns: Active patch; caller must call ``.deactivate()``.
    """
    decision = _FakeDecision(allowed=allowed)
    patch = create_module_patch(secrets_routes, "rbac_evaluator")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "check_permission", lambda **kwargs: decision
    )
    return patch


def _patch_list_returns(*, rows: List[_FakeRecord]) -> Any:
    """
        Patch ``secrets_routes.secrets_service.list_secrets`` to return
        ``rows`` directly so the handler body is reachable in happy path.

        :param rows: Records to return.

        :returns: Active patch; caller must call ``.deactivate()``.
    """
    patch = create_module_patch(secrets_routes, "secrets_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "list_secrets", lambda **kwargs: rows
    )
    return patch


# ---------------------------------------------------------------------------
# GET /api/v1/secrets  (list)
# ---------------------------------------------------------------------------


def test_list_secrets_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets returns 401 when no
    auth_principal is on the request.**
    """
    request = _FakeRequest(
        path="/api/v1/secrets",
        db_session=object(),
        auth_principal=None,
    )
    response = secrets_routes.handle_list_secrets(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_secrets_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets returns 403 when the caller is
    authenticated but does not hold system:secrets.read.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/secrets",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_list_secrets(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_list_secrets_returns_200_when_authorized():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets returns 200 with the metadata
    list when the caller holds system:secrets.read.**
    """
    record = _FakeRecord(secret_ref="alpha/k1")
    eval_patch = _patch_evaluator(allowed=True)
    svc_patch = _patch_list_returns(rows=[record])
    try:
        request = _FakeRequest(
            path="/api/v1/secrets",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_list_secrets(request)
    finally:
        eval_patch.deactivate()
        svc_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 1)
    testbase.assert_equal(body[0]["secret_ref"], "alpha/k1")
    return


# ---------------------------------------------------------------------------
# GET /api/v1/secrets/{secret_ref}  (metadata read)
# ---------------------------------------------------------------------------


def test_read_secret_returns_401_when_no_principal():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets/{ref} returns 401 when no
    auth_principal is on the request.**
    """
    request = _FakeRequest(
        path="/api/v1/secrets/my/key",
        path_params={"secret_ref": "my/key"},
        db_session=object(),
        auth_principal=None,
    )
    response = secrets_routes.handle_read_secret(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_read_secret_returns_403_when_permission_denied():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets/{ref} returns 403 when the
    caller does not hold system:secrets.read.**
    """
    eval_patch = _patch_evaluator(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/secrets/my/key",
            path_params={"secret_ref": "my/key"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_read_secret(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_read_secret_returns_200_when_authorized_and_record_exists():
    """
    **Feature: rest-auth-hardening hole #5**
    **Property: GET /api/v1/secrets/{ref} returns 200 with the
    metadata dict when the caller holds system:secrets.read and
    the record exists.**
    """
    record = _FakeRecord(secret_ref="my/key")
    db_session = _FakeDbSession(first_value=record)
    eval_patch = _patch_evaluator(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/secrets/my/key",
            path_params={"secret_ref": "my/key"},
            db_session=db_session,
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_read_secret(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["secret_ref"], "my/key")
    return
