"""
.. module:: test_p21a_webhooks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webhooks REST endpoints (PR p21a).

.. moduleauthor:: Code Craft AI LLC

Covers the inbound + outbound webhook routes attached by
``register_webhooks_in_routes`` and
``register_webhooks_out_routes``:

* POST   /api/v1/webhooks/in/{provider}/{hook_name}
* GET    /api/v1/webhooks/in/integrations
* POST   /api/v1/webhooks/in/integrations
* GET    /api/v1/webhooks/in/deliveries
* GET    /api/v1/webhooks/out/subscriptions
* POST   /api/v1/webhooks/out/subscriptions
* GET    /api/v1/webhooks/out/subscriptions/{id}
* DELETE /api/v1/webhooks/out/subscriptions/{id}
* GET    /api/v1/webhooks/out/subscriptions/{id}/deliveries
* POST   /api/v1/webhooks/out/subscriptions/{id}/test

The inbound receiver accepts a correctly-signed event, rejects a
bad signature with 401, and 409s a replay. The operator-facing
routes get auth (401/403), session (503), validation (422), and
not-found (404) coverage.
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

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.webhooks_in.dispatcher import (
    WebhookDispatchResult,
)
from ccai.pychestrate.webservice.webhooks_in.models import (
    StructuredRejection,
)
from ccai.pychestrate.webservice.webhooks_in.restapi.v1 import (
    webhooks_in_routes,
)
from ccai.pychestrate.webservice.webhooks_out.errors import (
    WebhookTargetConflictError,
    WebhookTargetInvalidError,
    WebhookTargetNotFoundError,
)
from ccai.pychestrate.webservice.webhooks_out.models import (
    DeliveryOutcome,
    SignatureScheme,
)
from ccai.pychestrate.webservice.webhooks_out.delivery import (
    SendResult,
)
from ccai.pychestrate.webservice.webhooks_out.restapi.v1 import (
    webhooks_out_routes,
)
from ccai.pychestrate.webservice.webhooks_out.service import (
    SignedRequest,
    WebhookDeliveryView,
    WebhookTargetView,
)
from ccai.pychestrate.webservice.webhooks_in.configuration_service import (
    WebhookConfigurationView,
)
from ccai.pychestrate.webservice.webhooks_in.errors import (
    WebhookConfigurationNotFoundError,
)


# Inbound ids are UUIDs: the inbound routes answer 422 / 404 for a
# malformed project or webhook id instead of failing in the driver.
INBOUND_PROJECT_ID: str = "00000000-0000-4000-8000-00000000a101"
INBOUND_WEBHOOK_ID: str = "00000000-0000-4000-8000-00000000a102"
INBOUND_UNKNOWN_WEBHOOK_ID: str = "00000000-0000-4000-8000-00000000a1ff"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeHeaders:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def items(self):
        rtnval = list(self._values.items())
        return rtnval

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
            raw_body: bytes = b"",
            headers: Optional[Dict[str, str]] = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.body: bytes = raw_body
        self.headers: _FakeHeaders = _FakeHeaders(values=headers)
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        rtnval = self._body
        return rtnval

    def get_header(
            self, name: str, default: Optional[str] = None
        ) -> Optional[str]:
        rtnval = self.headers.get(name, default)
        return rtnval


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


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool, reason: str = "") -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        return


class _FakeConfigRow:
    def __init__(
            self,
            *,
            secret_ref: str = "topsecret",
            provider: str = "generic",
            hook_name: str = "ops"
        ) -> None:
        self.secret_ref: str = secret_ref
        self.provider: str = provider
        self.hook_name: str = hook_name
        return


class _FakeTargetRow:
    def __init__(
            self,
            *,
            target_id: str = "sub-1",
            secret_ref: str = "topsecret",
            enabled: bool = True
        ) -> None:
        self.target_id: str = target_id
        self.secret_ref: str = secret_ref
        self.enabled: bool = enabled
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_in_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        webhooks_in_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_secret_resolution(*, value: Optional[bytes] = b"topsecret") -> Any:
    """
        Patch the receiver's vault lookup so a fake configuration
        row resolves to ``value``.
    """
    patch = create_module_patch(
        webhooks_in_routes.configuration_service, "resolve_shared_secret",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: value)
    return patch


def _patch_secret_stored(*, stored: bool = True) -> Any:
    """
        Patch the serializer's vault-existence check.
    """
    patch = create_module_patch(
        webhooks_in_routes.configuration_service, "is_secret_ref_stored",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: stored)
    return patch


def _patch_out_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        webhooks_out_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _make_config_view(
        *, webhook_id: str = INBOUND_WEBHOOK_ID
    ) -> WebhookConfigurationView:
    rtnval = WebhookConfigurationView(
        webhook_id=webhook_id,
        project_id=INBOUND_PROJECT_ID,
        provider="generic",
        hook_name="ops",
        secret_ref="topsecret",
        mtls_required=False,
        description="",
        enabled=True,
        created_by="user-1",
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        disabled_at=None,
    )
    return rtnval


def _make_target_view(
        *, target_id: str = "sub-1"
    ) -> WebhookTargetView:
    rtnval = WebhookTargetView(
        target_id=target_id,
        project_id="proj-1",
        name="ops-subscriber",
        description="",
        url="https://example.test/hook",
        signature_scheme=SignatureScheme.HMAC_SHA256,
        topic_filters=("entity.run.*",),
        enabled=True,
        custom_headers={},
        created_by="user-1",
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


def _make_delivery_view(
        *, delivery_id: str = "del-1"
    ) -> WebhookDeliveryView:
    rtnval = WebhookDeliveryView(
        delivery_id=delivery_id,
        target_id="sub-1",
        project_id="proj-1",
        topic="entity.webhook.test",
        payload_digest_sha256="a" * 64,
        signature="sha256=abc",
        request_headers={},
        outcome=DeliveryOutcome.PENDING,
        response_status=None,
        response_excerpt=None,
        duration_ms=None,
        attempted_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_webhooks_in_routes_attaches_five_endpoints():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: register_webhooks_in_routes attaches the five
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    webhooks_in_routes.register_webhooks_in_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/webhooks/in/integrations", ("GET",)),
        ("/api/v1/webhooks/in/integrations", ("POST",)),
        ("/api/v1/webhooks/in/integrations/{webhook_id}", ("PATCH",)),
        ("/api/v1/webhooks/in/deliveries", ("GET",)),
        ("/api/v1/webhooks/in/{provider}/{hook_name}", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_webhooks_out_routes_attaches_seven_endpoints():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: register_webhooks_out_routes attaches the seven
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    webhooks_out_routes.register_webhooks_out_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/webhooks/out/subscriptions", ("GET",)),
        ("/api/v1/webhooks/out/subscriptions", ("POST",)),
        ("/api/v1/webhooks/out/subscriptions/{subscription_id}", ("GET",)),
        ("/api/v1/webhooks/out/subscriptions/{subscription_id}", ("PATCH",)),
        ("/api/v1/webhooks/out/subscriptions/{subscription_id}", ("DELETE",)),
        (
            "/api/v1/webhooks/out/subscriptions/{subscription_id}/deliveries",
            ("GET",),
        ),
        (
            "/api/v1/webhooks/out/subscriptions/{subscription_id}/test",
            ("POST",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# Inbound receiver -- accept / reject / replay
# ---------------------------------------------------------------------------


def test_receiver_accepts_a_dispatched_event():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: a correctly-signed event dispatches and answers 202.**
    """
    cfg_patch = create_module_patch(
        webhooks_in_routes.repository,
        "list_active_configurations_for_provider",
    )
    cfg_mock = cfg_patch.activate()
    cfg_mock.configure(side_effect=lambda **kwargs: [_FakeConfigRow()])
    secret_patch = _patch_secret_resolution()
    disp_patch = create_module_patch(
        webhooks_in_routes, "dispatch_inbound_webhook",
    )
    disp_mock = disp_patch.activate()
    disp_mock.configure(
        side_effect=lambda **kwargs: WebhookDispatchResult(
            status="dispatched",
            request_id="req-1",
            provider="generic",
            hook_name="ops",
            delivery_id="del-1",
            domain_event_count=2,
            rejection=None,
            matched_signature_header="X-Sig",
        )
    )
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/generic/ops",
            path_params={"provider": "generic", "hook_name": "ops"},
            raw_body=b'{"event": "push"}',
            headers={"X-Sig": "sha256=good"},
            db_session=object(),
        )
        response = webhooks_in_routes.handle_receive_webhook(request)
    finally:
        disp_patch.deactivate()
        secret_patch.deactivate()
        cfg_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["status"], "accepted")
    testbase.assert_equal(body["domain_event_count"], 2)
    return


def test_receiver_rejects_bad_signature_with_401():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: a bad signature yields a 401 rejection.**
    """
    cfg_patch = create_module_patch(
        webhooks_in_routes.repository,
        "list_active_configurations_for_provider",
    )
    cfg_mock = cfg_patch.activate()
    cfg_mock.configure(side_effect=lambda **kwargs: [_FakeConfigRow()])
    secret_patch = _patch_secret_resolution()
    disp_patch = create_module_patch(
        webhooks_in_routes, "dispatch_inbound_webhook",
    )
    disp_mock = disp_patch.activate()
    disp_mock.configure(
        side_effect=lambda **kwargs: WebhookDispatchResult(
            status="rejected",
            request_id="req-1",
            provider="generic",
            hook_name="ops",
            delivery_id=None,
            domain_event_count=0,
            rejection=StructuredRejection(
                reason="signature_invalid",
                detail="bad",
                recoverable=False,
                status_code=401,
            ),
            matched_signature_header=None,
        )
    )
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/generic/ops",
            path_params={"provider": "generic", "hook_name": "ops"},
            raw_body=b'{"event": "push"}',
            headers={},
            db_session=object(),
        )
        response = webhooks_in_routes.handle_receive_webhook(request)
    finally:
        disp_patch.deactivate()
        secret_patch.deactivate()
        cfg_patch.deactivate()
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["status"], "rejected")
    testbase.assert_equal(body["reason"], "signature_invalid")
    return


def test_receiver_409s_a_replayed_delivery():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: a replayed delivery short-circuits with 409.**
    """
    cfg_patch = create_module_patch(
        webhooks_in_routes.repository,
        "list_active_configurations_for_provider",
    )
    cfg_mock = cfg_patch.activate()
    cfg_mock.configure(side_effect=lambda **kwargs: [_FakeConfigRow()])
    secret_patch = _patch_secret_resolution()
    disp_patch = create_module_patch(
        webhooks_in_routes, "dispatch_inbound_webhook",
    )
    disp_mock = disp_patch.activate()
    disp_mock.configure(
        side_effect=lambda **kwargs: WebhookDispatchResult(
            status="replay_ignored",
            request_id="req-1",
            provider="generic",
            hook_name="ops",
            delivery_id="del-1",
            domain_event_count=0,
            rejection=None,
            matched_signature_header="X-Sig",
        )
    )
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/generic/ops",
            path_params={"provider": "generic", "hook_name": "ops"},
            raw_body=b'{"event": "push"}',
            headers={"X-Sig": "sha256=good"},
            db_session=object(),
        )
        response = webhooks_in_routes.handle_receive_webhook(request)
    finally:
        disp_patch.deactivate()
        secret_patch.deactivate()
        cfg_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["status"], "replay_ignored")
    return


def test_receiver_404s_unknown_integration():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: an unknown provider/hook_name yields 404 without
    leaking integration existence.**
    """
    cfg_patch = create_module_patch(
        webhooks_in_routes.repository,
        "list_active_configurations_for_provider",
    )
    cfg_mock = cfg_patch.activate()
    cfg_mock.configure(side_effect=lambda **kwargs: [])
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/nope/ops",
            path_params={"provider": "nope", "hook_name": "ops"},
            raw_body=b"{}",
            headers={},
            db_session=object(),
        )
        response = webhooks_in_routes.handle_receive_webhook(request)
    finally:
        cfg_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "configuration_not_found")
    return


# ---------------------------------------------------------------------------
# Inbound integrations -- auth + validation
# ---------------------------------------------------------------------------


def test_list_integrations_returns_503_when_session_missing():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: GET integrations returns 503 with no db_session.**
    """
    request = _FakeRequest(
        path="/api/v1/webhooks/in/integrations",
        query={"project_id": "proj-1"},
        db_session=None,
    )
    response = webhooks_in_routes.handle_list_integrations(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_integrations_returns_401_when_no_principal():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: GET integrations returns 401 with no principal.**
    """
    request = _FakeRequest(
        path="/api/v1/webhooks/in/integrations",
        query={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = webhooks_in_routes.handle_list_integrations(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_integrations_returns_403_when_permission_denied():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: GET integrations returns 403 without
    system:webhooks.read.**
    """
    perm_patch = _patch_in_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            query={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_list_integrations(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:webhooks.read")
    return


def test_list_integrations_requires_project_id():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: GET integrations 422s without project_id.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            query={},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_list_integrations(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_list_integrations_happy_path():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: GET integrations returns a {items, meta} page.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    list_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "list_webhooks",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_config_view()])
    stored_patch = _patch_secret_stored(stored=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            query={"project_id": INBOUND_PROJECT_ID},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_list_integrations(request)
    finally:
        stored_patch.deactivate()
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["provider"], "generic")
    return


def test_list_integrations_rejects_a_malformed_project_id():
    """
    **Feature: 8-webhooks-in (audit ORC-29 follow-up)**
    **Property: GET integrations answers 422 for a project_id that is
    not a UUID instead of failing in the database driver.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            query={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_list_integrations(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_integration_validates_missing_fields():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: POST integrations 422s when required fields are
    missing.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            body={"provider": "generic"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_create_integration(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_integration_happy_path():
    """
    **Feature: 8-webhooks-in PR p21a**
    **Property: POST integrations returns 201 with the created
    integration.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    project_patch = create_module_patch(
        webhooks_in_routes.projects_repo, "get_project_by_id",
    )
    project_mock = project_patch.activate()
    project_mock.configure(side_effect=lambda **kwargs: object())
    create_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "create_webhook_with_secret",
    )
    create_mock = create_patch.activate()
    create_mock.configure(side_effect=lambda **kwargs: _make_config_view())
    stored_patch = _patch_secret_stored(stored=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            body={
                "project_id": INBOUND_PROJECT_ID,
                "provider": "generic",
                "hook_name": "ops",
                "secret": "topsecret",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_create_integration(request)
    finally:
        stored_patch.deactivate()
        create_patch.deactivate()
        project_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["webhook_id"], INBOUND_WEBHOOK_ID)
    return


def test_create_integration_404s_for_an_unknown_project():
    """
    **Feature: 8-webhooks-in (audit ORC-29 follow-up)**
    **Property: POST integrations answers 404 when the project does
    not exist, before any secret is stored.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    project_patch = create_module_patch(
        webhooks_in_routes.projects_repo, "get_project_by_id",
    )
    project_mock = project_patch.activate()
    project_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations",
            body={
                "project_id": INBOUND_PROJECT_ID,
                "provider": "generic",
                "hook_name": "ops",
                "secret": "topsecret",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_create_integration(request)
    finally:
        project_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


# ---------------------------------------------------------------------------
# Outbound subscriptions -- auth + validation + CRUD
# ---------------------------------------------------------------------------


def test_list_subscriptions_returns_401_when_no_principal():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: GET subscriptions returns 401 with no principal.**
    """
    request = _FakeRequest(
        path="/api/v1/webhooks/out/subscriptions",
        query={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = webhooks_out_routes.handle_list_subscriptions(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_subscriptions_returns_403_when_permission_denied():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: GET subscriptions returns 403 without
    system:webhooks.read.**
    """
    perm_patch = _patch_out_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            query={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_list_subscriptions(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:webhooks.read")
    return


def test_list_subscriptions_happy_path():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: GET subscriptions returns a {items, meta} page.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    list_patch = create_module_patch(
        webhooks_out_routes.out_service, "list_targets_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_target_view()])
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            query={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_list_subscriptions(request)
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["subscription_id"], "sub-1")
    return


def test_create_subscription_validates_missing_fields():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: POST subscriptions 422s when required fields are
    missing.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            body={"name": "ops"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_create_subscription(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_subscription_409s_on_conflict():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: POST subscriptions 409s on a duplicate name.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    create_patch = create_module_patch(
        webhooks_out_routes.out_service, "register_target",
    )
    create_mock = create_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise WebhookTargetConflictError("dup")

    create_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            body={
                "project_id": "proj-1",
                "name": "ops",
                "url": "https://example.test/hook",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_create_subscription(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    return


def test_create_subscription_happy_path():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: POST subscriptions returns 201 with the created
    subscription.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    create_patch = create_module_patch(
        webhooks_out_routes.out_service, "register_target",
    )
    create_mock = create_patch.activate()
    create_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            body={
                "project_id": "proj-1",
                "name": "ops-subscriber",
                "url": "https://example.test/hook",
                "topic_filters": ["entity.run.*"],
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_create_subscription(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["subscription_id"], "sub-1")
    return


def test_create_subscription_generates_signing_secret_when_absent():
    """
    **Feature: 8-webhooks-out**
    **Property: POST subscriptions with no secret_ref generates a
    signing secret, stores it as the target's secret_ref, and
    returns it exactly once as ``signing_secret`` on the 201
    response.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    create_patch = create_module_patch(
        webhooks_out_routes.out_service, "register_target",
    )
    create_mock = create_patch.activate()
    captured_kwargs: Dict[str, Any] = {}

    def _capture(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        rtnval = _make_target_view()
        return rtnval

    create_mock.configure(side_effect=_capture)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            body={
                "project_id": "proj-1",
                "name": "ops-subscriber",
                "url": "https://example.test/hook",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_create_subscription(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_true("signing_secret" in body)
    testbase.assert_equal(body["signing_secret"], captured_kwargs["secret_ref"])
    testbase.assert_equal(len(body["signing_secret"]), 64)
    return


def test_create_subscription_does_not_echo_supplied_secret_ref():
    """
    **Feature: 8-webhooks-out**
    **Property: POST subscriptions with a caller-supplied
    secret_ref never returns a ``signing_secret`` member -- an
    operator-managed secret is never echoed back.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    create_patch = create_module_patch(
        webhooks_out_routes.out_service, "register_target",
    )
    create_mock = create_patch.activate()
    create_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions",
            body={
                "project_id": "proj-1",
                "name": "ops-subscriber",
                "url": "https://example.test/hook",
                "secret_ref": "operator-supplied",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_create_subscription(request)
    finally:
        create_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_true("signing_secret" not in body)
    return


def test_update_subscription_enables_and_disables():
    """
    **Feature: 8-webhooks-out**
    **Property: PATCH subscription routes ``enabled`` to the
    matching service call and returns 200 with the subscription.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    enable_patch = create_module_patch(
        webhooks_out_routes.out_service, "enable_target",
    )
    enable_mock = enable_patch.activate()
    enable_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    disable_patch = create_module_patch(
        webhooks_out_routes.out_service, "disable_target",
    )
    disable_mock = disable_patch.activate()
    disable_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    try:
        enable_request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1",
            path_params={"subscription_id": "sub-1"},
            body={"enabled": True},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        enable_response = webhooks_out_routes.handle_update_subscription(
            enable_request
        )
        disable_request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1",
            path_params={"subscription_id": "sub-1"},
            body={"enabled": False},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        disable_response = webhooks_out_routes.handle_update_subscription(
            disable_request
        )
    finally:
        disable_patch.deactivate()
        enable_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(enable_response.status_code, 200)
    testbase.assert_equal(disable_response.status_code, 200)
    enable_body = _decode_body(enable_response)
    testbase.assert_equal(enable_body["subscription_id"], "sub-1")
    return


def test_update_subscription_422s_without_enabled():
    """
    **Feature: 8-webhooks-out**
    **Property: PATCH subscription 422s when ``enabled`` is
    missing or not a boolean.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1",
            path_params={"subscription_id": "sub-1"},
            body={"enabled": "yes"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_update_subscription(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_update_integration_enables_and_disables():
    """
    **Feature: 8-webhooks-in**
    **Property: PATCH integration routes ``enabled`` to the
    matching configuration-service call and returns 200 with the
    integration.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    enable_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "enable_webhook",
    )
    enable_mock = enable_patch.activate()
    enable_mock.configure(side_effect=lambda **kwargs: _make_config_view())
    disable_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "disable_webhook",
    )
    disable_mock = disable_patch.activate()
    disable_mock.configure(side_effect=lambda **kwargs: _make_config_view())
    stored_patch = _patch_secret_stored(stored=True)
    try:
        enable_request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations/" + INBOUND_WEBHOOK_ID,
            path_params={"webhook_id": INBOUND_WEBHOOK_ID},
            body={"enabled": True},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        enable_response = webhooks_in_routes.handle_update_integration(
            enable_request
        )
        disable_request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations/" + INBOUND_WEBHOOK_ID,
            path_params={"webhook_id": INBOUND_WEBHOOK_ID},
            body={"enabled": False},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        disable_response = webhooks_in_routes.handle_update_integration(
            disable_request
        )
    finally:
        stored_patch.deactivate()
        disable_patch.deactivate()
        enable_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(enable_response.status_code, 200)
    testbase.assert_equal(disable_response.status_code, 200)
    enable_body = _decode_body(enable_response)
    testbase.assert_equal(enable_body["webhook_id"], INBOUND_WEBHOOK_ID)
    return


def test_update_integration_404s_when_missing():
    """
    **Feature: 8-webhooks-in**
    **Property: PATCH integration 404s on an unknown webhook_id.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    disable_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "disable_webhook",
    )
    disable_mock = disable_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise WebhookConfigurationNotFoundError("nope")

    disable_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations/" + INBOUND_UNKNOWN_WEBHOOK_ID,
            path_params={"webhook_id": INBOUND_UNKNOWN_WEBHOOK_ID},
            body={"enabled": False},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_update_integration(request)
    finally:
        disable_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_update_integration_404s_for_a_malformed_webhook_id():
    """
    **Feature: 8-webhooks-in (audit ORC-29 follow-up)**
    **Property: PATCH integration answers 404 for a webhook_id that is
    not a UUID without reaching the configuration service.**
    """
    perm_patch = _patch_in_permission(allowed=True)
    disable_patch = create_module_patch(
        webhooks_in_routes.configuration_service, "disable_webhook",
    )
    disable_mock = disable_patch.activate()
    disable_mock.configure(side_effect=lambda **kwargs: _make_config_view())
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/in/integrations/wh-x",
            path_params={"webhook_id": "wh-x"},
            body={"enabled": False},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_in_routes.handle_update_integration(request)
    finally:
        disable_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_read_subscription_404_when_missing():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: GET subscription 404s on an unknown id.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    get_patch = create_module_patch(
        webhooks_out_routes.out_service, "get_target",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise WebhookTargetNotFoundError("nope")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-x",
            path_params={"subscription_id": "sub-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_read_subscription(request)
    finally:
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_delete_subscription_happy_path():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: DELETE subscription disables and returns 200.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    disable_patch = create_module_patch(
        webhooks_out_routes.out_service, "disable_target",
    )
    disable_mock = disable_patch.activate()
    disable_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1",
            path_params={"subscription_id": "sub-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_delete_subscription(request)
    finally:
        disable_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    return


def test_list_subscription_deliveries_happy_path():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: GET deliveries returns a {items, meta} page.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    get_patch = create_module_patch(
        webhooks_out_routes.out_service, "get_target",
    )
    get_mock = get_patch.activate()
    get_mock.configure(side_effect=lambda **kwargs: _make_target_view())
    list_patch = create_module_patch(
        webhooks_out_routes.out_service, "list_recent_deliveries_for_target",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_delivery_view()])
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1/deliveries",
            path_params={"subscription_id": "sub-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_list_subscription_deliveries(
            request,
        )
    finally:
        list_patch.deactivate()
        get_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["outcome"], "pending")
    return


def _run_test_delivery(*, sent: Any) -> Tuple[Any, List[Dict[str, Any]]]:
    """
        Drive POST .../test with the sender answering ``sent``; return
        the response and the record_delivery_attempt calls.
    """
    recorded: List[Dict[str, Any]] = []
    perm_patch = _patch_out_permission(allowed=True)
    find_patch = create_module_patch(
        webhooks_out_routes.repository, "find_target_by_id",
    )
    find_mock = find_patch.activate()
    find_mock.configure(side_effect=lambda **kwargs: _FakeTargetRow())
    signed_patch = create_module_patch(
        webhooks_out_routes.out_service, "build_signed_request",
    )
    signed_mock = signed_patch.activate()
    signed_mock.configure(
        side_effect=lambda **kwargs: SignedRequest(
            method="POST",
            url="https://example.test/hook",
            headers={"X-Pychestrate-Topic": "entity.webhook.test"},
            body=b"{}",
            signature="sha256=abc",
            payload_digest_sha256="a" * 64,
            delivery_id="del-1",
        )
    )
    send_patch = create_module_patch(
        webhooks_out_routes.out_delivery, "send_signed_request",
    )
    send_mock = send_patch.activate()
    send_mock.configure(side_effect=lambda **kwargs: sent)
    record_patch = create_module_patch(
        webhooks_out_routes.out_service, "record_delivery_attempt",
    )
    record_mock = record_patch.activate()

    def _record(**kwargs: Any) -> Any:
        recorded.append(kwargs)
        rtnval = _make_delivery_view()
        return rtnval

    record_mock.configure(side_effect=_record)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-1/test",
            path_params={"subscription_id": "sub-1"},
            raw_body=b"",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_test_subscription(request)
    finally:
        record_patch.deactivate()
        send_patch.deactivate()
        signed_patch.deactivate()
        find_patch.deactivate()
        perm_patch.deactivate()
    rtnval = (response, recorded)
    return rtnval


def test_test_subscription_records_a_delivered_test_event():
    """
    **Feature: outbound webhooks -- audit ORC-04**
    **Property: POST .../test sends the signed event and records the
    attempt with the receiver's answer -- a 2xx is recorded as
    succeeded (it was left "pending" forever before).**
    """
    response, recorded = _run_test_delivery(sent=SendResult(
        outcome=DeliveryOutcome.SUCCEEDED,
        response_status=204,
        response_excerpt="",
        duration_ms=12,
    ))
    body = _decode_body(response)
    testbase.assert_equal(
        (response.status_code, body["status"], recorded[0]["outcome"], recorded[0]["response_status"]),
        (200, "succeeded", DeliveryOutcome.SUCCEEDED, 204),
    )
    return


def test_test_subscription_records_an_undelivered_test_event():
    """
    **Feature: outbound webhooks -- audit ORC-04**
    **Property: when the test event is not delivered, the attempt is
    recorded as failed with the reason, and the response says so.**
    """
    response, recorded = _run_test_delivery(sent=SendResult(
        outcome=DeliveryOutcome.FAILED,
        response_status=None,
        response_excerpt="not sent: the URL targets the Pychestrate server itself (localhost)",
        duration_ms=0,
    ))
    body = _decode_body(response)
    testbase.assert_equal(
        (body["status"], recorded[0]["outcome"], recorded[0]["response_excerpt"].startswith("not sent:")),
        ("failed", DeliveryOutcome.FAILED, True),
    )
    return


def test_test_subscription_404_when_missing():
    """
    **Feature: 8-webhooks-out PR p21a**
    **Property: POST .../test 404s on an unknown subscription.**
    """
    perm_patch = _patch_out_permission(allowed=True)
    find_patch = create_module_patch(
        webhooks_out_routes.repository, "find_target_by_id",
    )
    find_mock = find_patch.activate()
    find_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/webhooks/out/subscriptions/sub-x/test",
            path_params={"subscription_id": "sub-x"},
            raw_body=b"",
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = webhooks_out_routes.handle_test_subscription(request)
    finally:
        find_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return
