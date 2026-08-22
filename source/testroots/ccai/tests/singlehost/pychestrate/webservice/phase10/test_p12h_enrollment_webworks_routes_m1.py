"""
.. module:: test_p12h_enrollment_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native enrollment REST routes.

.. moduleauthor:: Code Craft AI LLC

The enrollment port has the most exception types of any port so
far -- seven documented exception types across the redeem flow
alone -- plus base64 encode/decode helpers for CSR/PEM transport
and a fixed/parameterized path collision (``/redeem`` vs
``/{token_id}``). Tests cover the route matrix + ordering, the
503 sweep, the issue / list / revoke happy paths, the redeem
happy + each error path, the CSR base64 / PEM dual decode, the
client-revoke-under-enrollment surface, and bootstrap source-
smoke.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from ccai.pychestrate.webservice.clients.enums import (
    RevocationReason,
    TokenStatus,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    CertificateAuthorityUnavailableError,
    ClientAlreadyExistsError,
    ClientNotFoundError,
    CsrScopeMismatchError,
    CsrValidationError,
    EnrollmentRejectedError,
    EnrollmentTokenInvalidError,
    EnrollmentTokenNotFoundError,
)
from ccai.pychestrate.webservice.clients.restapi.v1 import (
    enrollment_routes,
)
from ccai.pychestrate.webservice.jobs.envelope import signer


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.actor_user_id: Optional[str] = actor_user_id
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


class _FakeIssued:
    def __init__(
        self,
        *,
        token_id: str = "tok-1",
        secret: str = "sek-secret",
        project_id: str = "p-1",
        pod_name: str = "pod-x",
    ) -> None:
        self.token_id: str = token_id
        self.secret: str = secret
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.expires_at_iso: str = "2026-05-04T12:00:00+00:00"
        self.algorithm_name: str = "hmac-sha256"
        return


class _FakeTokenView:
    def __init__(
        self,
        *,
        token_id: str = "tok-1",
        project_id: str = "p-1",
        pod_name: str = "pod-x",
        status: TokenStatus = TokenStatus.PENDING,
        one_shot: bool = True,
    ) -> None:
        self.token_id: str = token_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.status: TokenStatus = status
        self.issued_at_iso: str = "2026-05-03T12:00:00+00:00"
        self.expires_at_iso: str = "2026-05-04T12:00:00+00:00"
        self.one_shot: bool = one_shot
        self.algorithm_name: str = "hmac-sha256"
        self.redeemed_at_iso: Optional[str] = None
        self.redeemed_by_client_id: Optional[str] = None
        return


class _FakeRedemptionResult:
    def __init__(
        self,
        *,
        client_id: str = "c-1",
        project_id: str = "p-1",
        pod_name: str = "pod-x",
        bearer_token: str = "bearer-x",
        bearer_algorithm: str = "hmac-sha256",
        cert_serial: Optional[str] = None,
        cert_pem: Optional[bytes] = None,
        cert_chain_pem: Optional[bytes] = None,
    ) -> None:
        self.client_id: str = client_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.bearer_token: str = bearer_token
        self.bearer_algorithm: str = bearer_algorithm
        self.cert_serial: Optional[str] = cert_serial
        self.cert_pem: Optional[bytes] = cert_pem
        self.cert_chain_pem: Optional[bytes] = cert_chain_pem
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


def _patch_routes_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``enrollment_routes.<name>`` (the routes module's
        bound import) to the supplied callable.
    """
    patch = create_module_patch(enrollment_routes, name)
    mock = patch.activate()
    mock.configure(side_effect=value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_enrollment_routes_attaches_five_routes():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: register_enrollment_routes attaches the same five
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    enrollment_routes.register_enrollment_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/enrollment-tokens", ("GET",)),
        ("/api/v1/enrollment-tokens", ("POST",)),
        ("/api/v1/enrollment-tokens/redeem", ("POST",)),
        ("/api/v1/enrollment-tokens/clients/{client_id}/revoke", ("POST",)),
        ("/api/v1/enrollment-tokens/{token_id}", ("DELETE",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_enrollment_routes_declares_redeem_before_token_id_param():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: ``/redeem`` registers BEFORE ``/{token_id}``. Both
    live at depth 3 -- without the ordering, the webworks router
    would route ``POST /enrollment-tokens/redeem`` to a non-existent
    DELETE handler with token_id="redeem".**
    """
    app = _FakeApp()
    enrollment_routes.register_enrollment_routes(
        app=app, version_prefix="/api/v1"
    )
    redeem_index = None
    token_id_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/enrollment-tokens/redeem" and redeem_index is None:
            redeem_index = index
        if path == "/api/v1/enrollment-tokens/{token_id}" and token_id_index is None:
            token_id_index = index

    testbase.assert_equal(redeem_index < token_id_index, True)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_issue_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens",
        body={"project_id": "p-1", "pod_name": "pod-x", "ttl_seconds": 60},
        db_session=None,
    )
    response = enrollment_routes.handle_issue_enrollment_token(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_list_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens", db_session=None
    )
    response = enrollment_routes.handle_list_enrollment_tokens(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_revoke_token_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens/tok-1",
        path_params={"token_id": "tok-1"},
        db_session=None,
    )
    response = enrollment_routes.handle_revoke_enrollment_token(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_redeem_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens/redeem",
        body={"secret": "s", "pod_name": "pod-x"},
        db_session=None,
    )
    response = enrollment_routes.handle_redeem_enrollment_token(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_revoke_client_returns_503_when_session_missing():
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens/clients/c-1/revoke",
        path_params={"client_id": "c-1"},
        body={"reason": "rotated"},
        db_session=None,
    )
    response = enrollment_routes.handle_revoke_client_under_enrollment(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_issue_enrollment_token
# ---------------------------------------------------------------------------


def test_handle_issue_returns_201_with_secret_payload_and_actor_propagation():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Successful issue returns 201 with the token id +
    secret + scope + expiry; actor_user_id propagates as
    ``issued_by``.**
    """
    captured: Dict[str, Any] = {}

    def fake_issue(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeIssued(token_id="tok-1", secret="sek-secret")

    patch = _patch_routes_attr(
        name="issue_enrollment_token", value=fake_issue
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "project_id": "p-1",
                "pod_name": "pod-x",
                "ttl_seconds": 60,
                "one_shot": True,
            },
        )
        response = enrollment_routes.handle_issue_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["token_id"], "tok-1")
    testbase.assert_equal(body["secret"], "sek-secret")
    testbase.assert_equal(captured["issued_by"], "user-42")
    testbase.assert_equal(captured["one_shot"], True)
    return


def test_handle_issue_returns_400_when_ttl_not_positive():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: ttl_seconds <= 0 returns 400 problem+json with the
    bad value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens",
        db_session=object(),
        body={
            "project_id": "p-1", "pod_name": "pod-x", "ttl_seconds": 0,
        },
    )
    response = enrollment_routes.handle_issue_enrollment_token(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["ttl_seconds"], 0)
    return


def test_handle_issue_returns_400_on_undecodable_body():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Undecodable body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens",
        db_session=object(),
        body_raises=True,
    )
    response = enrollment_routes.handle_issue_enrollment_token(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_list_enrollment_tokens
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_views_with_no_filters():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Without filters list returns 200 with serialized
    views; project_id/status forwarded as None.**
    """
    captured: Dict[str, Any] = {}
    views = [
        _FakeTokenView(token_id="tok-1"),
        _FakeTokenView(token_id="tok-2", status=TokenStatus.REDEEMED),
    ]

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return views

    patch = _patch_routes_attr(name="list_enrollment_tokens", value=fake_list)
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens", db_session=object()
        )
        response = enrollment_routes.handle_list_enrollment_tokens(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(captured["project_id"], None)
    testbase.assert_equal(captured["status"], None)
    return


def test_handle_list_returns_400_with_status_extension_on_bad_status_filter():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Unknown status filter returns 400 problem+json
    with the raw value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens",
        db_session=object(),
        query={"status": "GARBAGE"},
    )
    response = enrollment_routes.handle_list_enrollment_tokens(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["requested_status"], "GARBAGE")
    return


def test_handle_list_propagates_filters():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: project_id + status query params propagate; status
    is enum-coerced.**
    """
    captured: Dict[str, Any] = {}

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return []

    patch = _patch_routes_attr(name="list_enrollment_tokens", value=fake_list)
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens",
            db_session=object(),
            query={"project_id": "p-7", "status": "PENDING"},
        )
        enrollment_routes.handle_list_enrollment_tokens(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["project_id"], "p-7")
    testbase.assert_equal(captured["status"], TokenStatus.PENDING)
    return


# ---------------------------------------------------------------------------
# handle_revoke_enrollment_token
# ---------------------------------------------------------------------------


def test_handle_revoke_token_returns_200_with_status_revoked():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Successful token revoke returns 200 with
    ``{token_id, status: revoked}``; actor propagates.**
    """
    captured: Dict[str, Any] = {}

    def fake_revoke(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_routes_attr(name="revoke_enrollment_token", value=fake_revoke)
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/tok-1",
            path_params={"token_id": "tok-1"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = enrollment_routes.handle_revoke_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["token_id"], "tok-1")
    testbase.assert_equal(body["status"], "revoked")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_revoke_token_returns_404_with_token_id_extension():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: EnrollmentTokenNotFoundError → 404 problem+json
    with the token_id as an extension member.**
    """
    patch = _patch_routes_attr(
        name="revoke_enrollment_token",
        value=_raises(EnrollmentTokenNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/tok-missing",
            path_params={"token_id": "tok-missing"},
            db_session=object(),
        )
        response = enrollment_routes.handle_revoke_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["token_id"], "tok-missing")
    return


# ---------------------------------------------------------------------------
# handle_redeem_enrollment_token
# ---------------------------------------------------------------------------


def test_handle_redeem_returns_200_with_bearer_token():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Successful redeem returns 200 with the bearer
    token + algorithm + empty cert fields when no CSR was
    submitted.**
    """
    result = _FakeRedemptionResult(
        client_id="c-1", bearer_token="bearer-x"
    )
    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=lambda **kwargs: result,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={
                "secret": "sek-secret",
                "pod_name": "pod-x",
                "agent_version": "1.0.0",
            },
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    testbase.assert_equal(body["bearer_token"], "bearer-x")
    testbase.assert_equal(body["cert_serial"], "")
    testbase.assert_equal(body["cert_pem"], "")
    testbase.assert_equal(body["cert_chain_pem"], "")
    return


def test_handle_redeem_decodes_pem_csr_and_emits_base64_cert():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: A raw PEM csr_pem field flows through as bytes;
    the response encodes the issued cert PEM as base64 for
    transport.**
    """
    cert_pem_bytes = b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
    result = _FakeRedemptionResult(
        cert_serial="aabbccdd",
        cert_pem=cert_pem_bytes,
        cert_chain_pem=b"chain-bytes",
    )
    captured: Dict[str, Any] = {}

    def fake_redeem(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return result

    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=fake_redeem,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={
                "secret": "sek-secret",
                "pod_name": "pod-x",
                "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nabc\n-----END CERTIFICATE REQUEST-----",
            },
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["cert_serial"], "aabbccdd")
    decoded_cert = base64.b64decode(body["cert_pem"])
    testbase.assert_equal(decoded_cert, cert_pem_bytes)
    decoded_chain = base64.b64decode(body["cert_chain_pem"])
    testbase.assert_equal(decoded_chain, b"chain-bytes")
    submitted_csr = captured["payload"].csr_pem
    testbase.assert_equal(
        submitted_csr.startswith(b"-----BEGIN CERTIFICATE REQUEST-----"),
        True,
    )
    return


def test_handle_redeem_decodes_base64_csr_field():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: A base64-encoded csr_pem field is decoded to bytes
    before being forwarded to the service.**
    """
    raw_pem = b"-----BEGIN CERTIFICATE REQUEST-----\nabc\n-----END CERTIFICATE REQUEST-----"
    encoded = base64.b64encode(raw_pem).decode("ascii")
    captured: Dict[str, Any] = {}

    def fake_redeem(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeRedemptionResult()

    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=fake_redeem,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={
                "secret": "sek-secret",
                "pod_name": "pod-x",
                "csr_pem": encoded,
            },
        )
        enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["payload"].csr_pem, raw_pem)
    return


def test_handle_redeem_returns_400_on_malformed_csr_field():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: A csr_pem field that is neither PEM text nor valid
    base64 returns 400 problem+json.**
    """
    # Use binary that base64 cannot decode -- the controller's
    # base64.b64decode(validate=False) is permissive on padding but
    # raises on non-alphabet bytes when given truly garbage input.
    # The PEM check requires "-----BEGIN" prefix, so a short
    # garbage string fails the PEM check too.

    class _GarbageStr(str):
        pass

    # We patch the b64decode to raise so we exercise the
    # except-branch deterministically.
    import ccai.pychestrate.webservice.clients.restapi.v1.enrollment_routes as er
    original_decode = base64.b64decode

    def fake_decode(*args: Any, **kwargs: Any) -> bytes:
        raise ValueError("not valid base64")

    base64.b64decode = fake_decode  # type: ignore[assignment]
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={
                "secret": "sek-secret",
                "pod_name": "pod-x",
                "csr_pem": "garbage-not-pem",
            },
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        base64.b64decode = original_decode  # type: ignore[assignment]

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_redeem_returns_404_on_token_not_found():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(EnrollmentTokenNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    return


def test_handle_redeem_returns_400_on_invalid_token():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(EnrollmentTokenInvalidError("bad")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_redeem_returns_403_on_enrollment_rejected():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(EnrollmentRejectedError("denied")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_handle_redeem_returns_409_on_client_already_exists():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(ClientAlreadyExistsError("dup")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    return


def test_handle_redeem_returns_403_on_csr_scope_mismatch():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(CsrScopeMismatchError("scope mismatch")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    return


def test_handle_redeem_returns_400_on_csr_validation_error():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(CsrValidationError("bad csr")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_redeem_returns_503_on_ca_unavailable():
    patch = _patch_routes_attr(
        name="redeem_enrollment_token",
        value=_raises(CertificateAuthorityUnavailableError("ca down")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "s", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_redeem_bundles_envelope_signing_keys_when_signer_installed():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: When the envelope signer is installed, a successful
    redeem bundles the JWKS-style ``envelope_signing_keys`` set so
    the freshly-enrolled client can verify signed envelopes without
    an extra call.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-redeem-key")
    signer.set_active_signing_key(handle=handle)

    result = _FakeRedemptionResult(client_id="c-1", bearer_token="bearer-x")
    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=lambda **kwargs: result,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "sek-secret", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()
        signer.reset_for_testing()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    keys = body["envelope_signing_keys"]
    testbase.assert_equal(len(keys), 1)
    testbase.assert_equal(keys[0]["key_id"], "p19k-redeem-key")
    testbase.assert_equal(keys[0]["algorithm"], "Ed25519")
    testbase.assert_equal(keys[0]["status"], "active")
    pem_ok = keys[0]["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
    testbase.assert_equal(pem_ok, True)
    return


def test_handle_redeem_emits_empty_signing_keys_when_signer_absent():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: With no signing key provisioned the redeem response
    still succeeds and carries an empty ``envelope_signing_keys``
    list -- the client refreshes via GET /envelope-signing-keys.**
    """
    signer.reset_for_testing()

    result = _FakeRedemptionResult(client_id="c-1")
    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=lambda **kwargs: result,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "sek-secret", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["envelope_signing_keys"], [])
    return


# ---------------------------------------------------------------------------
# handle_revoke_client_under_enrollment
# ---------------------------------------------------------------------------


def test_handle_revoke_client_under_enrollment_returns_200_on_success():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Successful client revoke returns 200 with
    ``{client_id, status: revoked, cert_serial, reason}``.
    cert_serial defaults to empty when none supplied.**
    """
    captured: Dict[str, Any] = {}

    def fake_revoke(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_routes_attr(name="revoke_client", value=fake_revoke)
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/clients/c-1/revoke",
            path_params={"client_id": "c-1"},
            db_session=object(),
            actor_user_id="user-42",
            body={
                "reason": "ROTATED",
                "note": "scheduled rotation",
                "cert_serial": "aabb",
            },
        )
        response = enrollment_routes.handle_revoke_client_under_enrollment(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    testbase.assert_equal(body["status"], "revoked")
    testbase.assert_equal(body["cert_serial"], "aabb")
    testbase.assert_equal(body["reason"], "ROTATED")
    testbase.assert_equal(captured["reason"], RevocationReason.ROTATED)
    testbase.assert_equal(captured["revoked_by"], "user-42")
    testbase.assert_equal(captured["note"], "scheduled rotation")
    return


def test_handle_revoke_client_under_enrollment_returns_400_when_reason_missing():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Missing reason returns 400 problem+json with
    client_id extension.**
    """
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens/clients/c-1/revoke",
        path_params={"client_id": "c-1"},
        db_session=object(),
        body={},
    )
    response = enrollment_routes.handle_revoke_client_under_enrollment(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-1")
    return


def test_handle_revoke_client_under_enrollment_returns_400_on_unknown_reason():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: Unknown reason returns 400 problem+json with the
    raw reason + accepted-list as extension members.**
    """
    request = _FakeRequest(
        path="/api/v1/enrollment-tokens/clients/c-1/revoke",
        path_params={"client_id": "c-1"},
        db_session=object(),
        body={"reason": "GARBAGE"},
    )
    response = enrollment_routes.handle_revoke_client_under_enrollment(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "GARBAGE")
    has_accepted = "accepted" in body
    testbase.assert_equal(has_accepted, True)
    return


def test_handle_revoke_client_under_enrollment_returns_404_on_unknown_client():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: ClientNotFoundError → 404 problem+json with
    client_id extension.**
    """
    patch = _patch_routes_attr(
        name="revoke_client",
        value=_raises(ClientNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/clients/c-missing/revoke",
            path_params={"client_id": "c-missing"},
            db_session=object(),
            body={"reason": "ROTATED"},
        )
        response = enrollment_routes.handle_revoke_client_under_enrollment(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], "c-missing")
    return


def test_handle_revoke_client_under_enrollment_treats_empty_cert_serial_as_none():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: An empty-string cert_serial in the body collapses
    to None when forwarded to revoke_client. Mirrors the flask
    controller's empty-string-equals-unset semantic.**
    """
    captured: Dict[str, Any] = {}

    def fake_revoke(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_routes_attr(name="revoke_client", value=fake_revoke)
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/clients/c-1/revoke",
            path_params={"client_id": "c-1"},
            db_session=object(),
            body={"reason": "ROTATED", "cert_serial": ""},
        )
        enrollment_routes.handle_revoke_client_under_enrollment(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["cert_serial"], None)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_enrollment_routes_and_calls_it():
    """
    **Feature: 3-client-enrollment T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_enrollment_routes into register_service_extensions.**
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
        "from ccai.pychestrate.webservice.clients.restapi.v1.enrollment_routes import"
        in text
    )
    has_call = "register_enrollment_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


def test_handle_redeem_reads_the_bootstrap_secret_field():
    """
    **Feature: client enrollment contract**
    **Property: The redeem handler reads the ``bootstrap_secret``
    body field -- the name the OpenAPI contract declares required
    for this operation and the name pychestrate-client sends. The
    handler previously read only ``secret``, so every real
    enrollment was rejected with "empty secret" and no pod could
    enroll, while the suite stayed green because the tests spoke
    the implementation's private spelling rather than the
    published contract.**
    """
    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        rtnval = _FakeRedemptionResult(client_id="c-1")
        return rtnval

    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=_capture,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={
                "bootstrap_secret": "contract-secret",
                "pod_name": "pod-x",
            },
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(seen["secret"], "contract-secret")
    return


def test_handle_redeem_still_accepts_the_legacy_secret_field():
    """
    **Feature: client enrollment contract**
    **Property: ``secret`` remains accepted as an alias for
    ``bootstrap_secret`` so callers written against the handler's
    original behavior keep working. Pinned deliberately: the alias
    is back-compat, not contract -- ``bootstrap_secret`` is the
    documented field.**
    """
    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        rtnval = _FakeRedemptionResult(client_id="c-1")
        return rtnval

    patch = _patch_routes_attr(
        name="redeem_enrollment_token", value=_capture,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/enrollment-tokens/redeem",
            db_session=object(),
            body={"secret": "legacy-secret", "pod_name": "pod-x"},
        )
        response = enrollment_routes.handle_redeem_enrollment_token(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(seen["secret"], "legacy-secret")
    return
