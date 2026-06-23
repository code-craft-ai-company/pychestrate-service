"""
.. module:: test_p11e3_secrets_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native secrets metadata routes.

.. moduleauthor:: Code Craft AI LLC

The secrets port exposes metadata only — never plaintext. Tests
cover the route matrix (note the ``:path`` converter on the
secret_ref so multi-segment refs route correctly), the 503
misconfig path, the list happy path, the detail happy path, the
404 path with secret_ref extension, and the bootstrap source-smoke.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from ccai.pychestrate.webservice.secrets.restapi.v1 import secrets_routes


class _FakePrincipal:
    def __init__(self, *, user_id: str = "caller-1") -> None:
        self.user_id: str = user_id
        self.session_id: str = "sess-caller-1"
        return


class _FakeAllowedDecision:
    def __init__(self) -> None:
        self.allowed: bool = True
        self.reason: str = "test-allow"
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
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: Dict[str, Any] = (
            query_params if query_params is not None else {}
        )
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return


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


class _FakeScopeKind:
    """
        Minimal stand-in for :class:`SecretScopeKind` — carries a
        ``.value`` attribute the route serializer reads.
    """

    def __init__(self, value: str) -> None:
        self.value: str = value
        return


class _FakeRecord:
    def __init__(
        self,
        *,
        secret_ref: str,
        backend_name: str = "vault",
        current_version_id: Optional[str] = None,
        scope_kind: str = "ORG",
        scope_ref: Optional[str] = None,
    ) -> None:
        self.secret_ref: str = secret_ref
        self.backend_name: str = backend_name
        self.current_version_id: Optional[str] = current_version_id
        self.scope_kind: _FakeScopeKind = _FakeScopeKind(scope_kind)
        self.scope_ref: Optional[str] = scope_ref
        self.created_at: datetime = datetime(
            2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeQuery:
    def __init__(
        self,
        *,
        rows: List[_FakeRecord],
        first_value: Optional[_FakeRecord] = None,
    ) -> None:
        self._rows = rows
        self._first_value = first_value
        return

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def all(self) -> List[_FakeRecord]:
        return list(self._rows)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Optional[_FakeRecord]:
        return self._first_value


class _FakeSession:
    def __init__(
        self,
        *,
        rows: Optional[List[_FakeRecord]] = None,
        first_value: Optional[_FakeRecord] = None,
    ) -> None:
        self._query = _FakeQuery(
            rows=rows if rows is not None else [],
            first_value=first_value,
        )
        return

    def query(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self._query


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_secrets_routes_attaches_full_crud_matrix():
    """
    **Feature: 1-secrets-vault PR p20g (scope-aware CRUD routes)**
    **Property: register_secrets_routes attaches the full CRUD matrix
    -- list + create on the collection, the dedicated value-read
    route, and metadata-read / update / delete on the parameterized
    ``:path`` route so multi-segment refs (``project/team/key``)
    match.**
    """
    app = _FakeApp()
    secrets_routes.register_secrets_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/secrets", ("GET",)),
        ("/api/v1/secrets", ("POST",)),
        ("/api/v1/secrets/value/{secret_ref:path}", ("GET",)),
        ("/api/v1/secrets/{secret_ref:path}", ("GET",)),
        ("/api/v1/secrets/{secret_ref:path}", ("PUT",)),
        ("/api/v1/secrets/{secret_ref:path}", ("DELETE",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_secrets_routes_declares_fixed_prefixes_before_parameterized():
    """
    **Feature: 1-secrets-vault PR p20g (scope-aware CRUD routes)**
    **Property: The fixed ``/secrets`` collection AND the fixed
    ``/secrets/value/...`` value route register BEFORE the
    parameterized ``:path`` route. With ``:path`` matching multiple
    segments the ordering avoids a greedy match swallowing the fixed
    prefixes.**
    """
    app = _FakeApp()
    secrets_routes.register_secrets_routes(
        app=app, version_prefix="/api/v1"
    )
    fixed_index = None
    value_index = None
    parameterized_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/secrets" and fixed_index is None:
            fixed_index = index
        if (
            path == "/api/v1/secrets/value/{secret_ref:path}"
            and value_index is None
        ):
            value_index = index
        if (
            path == "/api/v1/secrets/{secret_ref:path}"
            and parameterized_index is None
        ):
            parameterized_index = index

    testbase.assert_equal(fixed_index < parameterized_index, True)
    testbase.assert_equal(value_index < parameterized_index, True)
    return


# ---------------------------------------------------------------------------
# Misconfig
# ---------------------------------------------------------------------------


def test_handle_list_returns_401_when_principal_missing():
    """
    **Feature: 1-secrets-vault T1.1 auth hardening**
    **Property: A request with no auth_principal returns 401. The
    auth check now fires before the session check.**
    """
    request = _FakeRequest(
        path="/api/v1/secrets",
        db_session=None,
        auth_principal=None,
    )
    response = secrets_routes.handle_list_secrets(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_handle_list_returns_503_when_session_missing():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: A request with auth_principal present but no
    db_session returns 503 (middleware misconfiguration).**
    """
    request = _FakeRequest(
        path="/api/v1/secrets",
        db_session=None,
        auth_principal=_FakePrincipal(),
    )
    response = secrets_routes.handle_list_secrets(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_read_returns_401_when_principal_missing():
    """
    **Feature: 1-secrets-vault T1.1 auth hardening**
    **Property: detail handler returns 401 when auth_principal is
    absent.**
    """
    request = _FakeRequest(
        path="/api/v1/secrets/x",
        path_params={"secret_ref": "x"},
        db_session=None,
        auth_principal=None,
    )
    response = secrets_routes.handle_read_secret(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_handle_read_returns_503_when_session_missing():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: detail handler returns 503 when auth_principal is
    present but db_session is missing.**
    """
    request = _FakeRequest(
        path="/api/v1/secrets/x",
        path_params={"secret_ref": "x"},
        db_session=None,
        auth_principal=_FakePrincipal(),
    )
    response = secrets_routes.handle_read_secret(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_list_secrets
# ---------------------------------------------------------------------------


def _patch_evaluator_allow(module: Any) -> Any:
    """
        Patch ``<module>.rbac_evaluator.check_permission`` so it always
        returns an allowed decision.

        :param module: The route module (secrets_routes) whose
                       ``rbac_evaluator`` attribute is patched.

        :returns: Active patch object; caller must call
                  ``patch.deactivate()``.
    """
    allowed_decision = _FakeAllowedDecision()
    patch = create_module_patch(module, "rbac_evaluator")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "check_permission", lambda **kwargs: allowed_decision
    )
    return patch


def _patch_list_secrets(*, rows: List[Any]) -> Any:
    """
        Patch ``secrets_routes.secrets_service.list_secrets`` to return
        ``rows`` without touching the DB.

        :param rows: Rows to return.

        :returns: Active patch object; caller must call
                  ``patch.deactivate()``.
    """
    patch = create_module_patch(secrets_routes, "secrets_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(
        "list_secrets", lambda **kwargs: rows
    )
    return patch


def test_handle_list_returns_serialized_metadata_only():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: List returns 200 with metadata dicts. The wire
    response NEVER carries plaintext -- only the documented metadata
    fields. Now requires auth_principal + system:secrets.read
    (evaluator patched to allow).**
    """
    rows = [
        _FakeRecord(secret_ref="alpha/key-1", backend_name="vault"),
        _FakeRecord(secret_ref="beta/key-2", backend_name="vault"),
    ]
    eval_patch = _patch_evaluator_allow(module=secrets_routes)
    svc_patch = _patch_list_secrets(rows=rows)
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
    testbase.assert_equal(len(body), 2)
    expected_keys = sorted([
        "secret_ref", "backend_name", "scope_kind", "scope_ref",
        "current_version_id", "created_at", "updated_at",
    ])
    actual_keys = sorted(list(body[0].keys()))
    testbase.assert_equal(actual_keys, expected_keys)
    return


# ---------------------------------------------------------------------------
# handle_read_secret
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_record_on_match():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: A known secret_ref (multi-segment) returns 200 with
    metadata dict. Now requires auth_principal + system:secrets.read
    (evaluator patched to allow).**
    """
    record = _FakeRecord(
        secret_ref="project/team/db-password",
        backend_name="vault",
        current_version_id="ver-7",
    )
    session = _FakeSession(first_value=record)
    eval_patch = _patch_evaluator_allow(module=secrets_routes)
    try:
        request = _FakeRequest(
            path="/api/v1/secrets/project/team/db-password",
            path_params={"secret_ref": "project/team/db-password"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_read_secret(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["secret_ref"], "project/team/db-password")
    testbase.assert_equal(body["current_version_id"], "ver-7")
    return


def test_handle_read_returns_404_with_secret_ref_extension():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: An unknown secret_ref returns 404 problem+json with
    the secret_ref as an extension member. Evaluator patched to
    allow so the DB lookup is reached.**
    """
    session = _FakeSession(first_value=None)
    eval_patch = _patch_evaluator_allow(module=secrets_routes)
    try:
        request = _FakeRequest(
            path="/api/v1/secrets/missing",
            path_params={"secret_ref": "missing"},
            db_session=session,
            auth_principal=_FakePrincipal(),
        )
        response = secrets_routes.handle_read_secret(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["secret_ref"], "missing")
    is_json_response = isinstance(response, JSONResponse)
    testbase.assert_equal(is_json_response, True)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_secrets_routes_and_calls_it():
    """
    **Feature: 1-secrets-vault T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_secrets_routes
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
        "from ccai.pychestrate.webservice.secrets.restapi.v1.secrets_routes import"
        in text
    )
    has_call = "register_secrets_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
