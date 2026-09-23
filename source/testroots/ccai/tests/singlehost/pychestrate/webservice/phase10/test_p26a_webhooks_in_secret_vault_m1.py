"""
.. module:: test_p26a_webhooks_in_secret_vault_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression tests for audit ORC-29 -- an inbound
               webhook's shared secret lives only in the secrets
               vault and no API returns it.

.. moduleauthor:: Code Craft AI LLC

Before the fix the integration's ``secret_ref`` column held the
literal HMAC key, the receiver used that string as the key, and
``GET /api/v1/webhooks/in/integrations`` echoed it back. These
tests drive the real configuration service, secrets vault, and
REST handlers against an in-memory database:

* ``secrets_service.read_secret_for_service`` resolves a vault
  secret for in-process service code;
* a create stores the caller's ``secret`` in the vault and keeps
  only the vault reference;
* create / list responses never carry the key, and a stored value
  that is not a vault reference is never echoed;
* binding an existing ``secret_ref`` needs a readable vault secret;
* the receiver verifies deliveries with the vault-resolved key.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import json
import uuid as uuidmod

from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.projects.models import Project, ProjectState
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import (
    SecretNotFoundError,
    SecretVersionExpiredError,
)
from ccai.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    reset_active_kek_for_testing,
    set_active_kek,
)
from ccai.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretScopeKind,
    SecretVersion,
    SecretVersionState,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import (
    build_default_aspects,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import (
    AuthPrincipal,
)
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)
from ccai.pychestrate.webservice.webhooks_in import (
    register_builtin_extensions as webhooks_in_register,
)
from ccai.pychestrate.webservice.webhooks_in import configuration_service
from ccai.pychestrate.webservice.webhooks_in.models import (
    WebhookConfiguration,
)
from ccai.pychestrate.webservice.webhooks_in.restapi.v1 import (
    webhooks_in_routes,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


SHARED_KEY: str = "inbound-hmac-key-4d1f9c"
PROVIDER: str = "generic"
HOOK_NAME: str = "ops"


# ---------------------------------------------------------------------------
# Fakes + fixtures
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
            db_session: Any,
            auth_principal: Optional[Any] = None,
            body: Any = None,
            raw_body: bytes = b"",
            query: Optional[Dict[str, str]] = None,
            path_params: Optional[Dict[str, str]] = None,
            headers: Optional[Dict[str, str]] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, str] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.body: bytes = raw_body
        self.headers: _FakeHeaders = _FakeHeaders(values=headers)
        self.db_session: Any = db_session
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


class _Decision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        self.reason: str = ""
        return


def _patch_only_webhooks_write() -> Any:
    """
        Patch the shared rbac_evaluator so the caller holds
        ``system:webhooks.write`` and nothing else.

        :returns: The active patch (deactivate it when done).
    """
    patch = create_module_patch(
        webhooks_in_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(
        side_effect=lambda **kwargs: _Decision(
            allowed=kwargs.get("permission_key") == "system:webhooks.write",
        )
    )
    rtnval = patch
    return rtnval


def _install_test_kek() -> None:
    reset_active_kek_for_testing()
    set_active_kek(kek=KekHandle(
        kek_id="test-kek-orc29",
        key_material=SecretBytes(b"K" * 32),
        source="test",
    ))
    return


def _principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id=user_id,
        session_id="sess-orc29",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def _bind_system_admin(*, session: Any, user_id: str) -> None:
    role = (
        session.query(RbacRole)
        .filter(RbacRole.role_name == "system-admin")
        .first()
    )
    if role is None:
        role = RbacRole(
            role_id=new_uuid(),
            role_name="system-admin",
            source=RoleSource.BUILTIN,
            source_name="CorePermissionExtension",
            description="",
        )
        session.add(role)
        session.flush()
    session.add(RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=None,
    ))
    session.commit()
    return


def _add_project(*, session: Any) -> str:
    project_id = str(uuidmod.uuid4())
    session.add(Project(
        project_id=project_id,
        slug="orc29-" + project_id[:8],
        display_name="ORC-29",
        state=ProjectState.ACTIVE,
    ))
    session.commit()
    rtnval = project_id
    return rtnval


def _prepare() -> Any:
    """
        Fresh registry + KEK + in-memory database with an admin and
        a project.

        :returns: ``(session, admin_principal, project_id)``.
    """
    reset_phase1_runtime()
    webhooks_in_register()
    _install_test_kek()
    _engine, session = build_in_memory_session()
    admin_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)
    project_id = _add_project(session=session)
    rtnval = (session, _principal(admin_id), project_id)
    return rtnval


def _create_via_route(
        *,
        session: Any,
        principal: Any,
        body: Dict[str, Any]
    ) -> Any:
    request = _FakeRequest(
        path="/api/v1/webhooks/in/integrations",
        db_session=session,
        auth_principal=principal,
        body=body,
    )
    rtnval = webhooks_in_routes.handle_create_integration(request)
    return rtnval


def _list_via_route(*, session: Any, principal: Any, project_id: str) -> Any:
    request = _FakeRequest(
        path="/api/v1/webhooks/in/integrations",
        db_session=session,
        auth_principal=principal,
        query={"project_id": project_id},
    )
    rtnval = webhooks_in_routes.handle_list_integrations(request)
    return rtnval


def _receive_via_route(*, session: Any, body: bytes, key: bytes, delivery_id: str) -> Any:
    digest = hmac.new(key=key, msg=body, digestmod=hashlib.sha256).hexdigest()
    request = _FakeRequest(
        path="/api/v1/webhooks/in/{}/{}".format(PROVIDER, HOOK_NAME),
        db_session=session,
        path_params={"provider": PROVIDER, "hook_name": HOOK_NAME},
        raw_body=body,
        headers={
            "X-Pychestrate-Signature": "sha256=" + digest,
            "X-Pychestrate-Delivery-Id": delivery_id,
            "X-Pychestrate-Hook-Name": HOOK_NAME,
            "Content-Type": "application/json",
        },
    )
    rtnval = webhooks_in_routes.handle_receive_webhook(request)
    return rtnval


def _create_with_secret(*, session: Any, principal: Any, project_id: str) -> Any:
    rtnval = configuration_service.create_webhook_with_secret(
        db_session=session,
        principal=principal,
        project_id=project_id,
        provider=PROVIDER,
        hook_name=HOOK_NAME,
        shared_secret=SecretBytes(SHARED_KEY.encode("utf-8")),
    )
    return rtnval


def _body_text(response: Any) -> str:
    rtnval = response.body.decode("utf-8")
    return rtnval


# ---------------------------------------------------------------------------
# secrets_service.read_secret_for_service
# ---------------------------------------------------------------------------


def test_read_secret_for_service_returns_the_active_plaintext():
    """
    **Feature: audit ORC-29 / 1-secrets-vault**
    **Property: read_secret_for_service decrypts the active version of
    a vault secret without a principal.**
    """
    session, admin, _project_id = _prepare()
    secrets_service.put_secret(
        db_session=session,
        principal=admin,
        secret_ref="org:orc29.key",
        plaintext=SecretBytes(b"service-readable"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.ORG,
    )
    read = secrets_service.read_secret_for_service(
        db_session=session,
        secret_ref="org:orc29.key",
        service_identity="webhooks_in",
    )
    testbase.assert_equal(read.plaintext.reveal(), b"service-readable")
    return


def test_read_secret_for_service_raises_not_found_for_unknown_ref():
    """
    **Feature: audit ORC-29 / 1-secrets-vault**
    **Property: read_secret_for_service raises SecretNotFoundError for
    a reference with no vault record.**
    """
    session, _admin, _project_id = _prepare()
    raised = False
    try:
        secrets_service.read_secret_for_service(
            db_session=session,
            secret_ref="no-such-secret",
            service_identity="webhooks_in",
        )
    except SecretNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_secret_for_service_refuses_an_expired_version():
    """
    **Feature: audit ORC-29 / 1-secrets-vault**
    **Property: read_secret_for_service raises SecretVersionExpiredError
    when the active version is expired.**
    """
    session, admin, _project_id = _prepare()
    secrets_service.put_secret(
        db_session=session,
        principal=admin,
        secret_ref="org:orc29.expiring",
        plaintext=SecretBytes(b"old"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.ORG,
    )
    version = (
        session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == "org:orc29.expiring")
        .first()
    )
    version.state = SecretVersionState.EXPIRED
    session.commit()
    raised = False
    try:
        secrets_service.read_secret_for_service(
            db_session=session,
            secret_ref="org:orc29.expiring",
            service_identity="webhooks_in",
        )
    except SecretVersionExpiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Create: the key goes to the vault, the row keeps only the reference
# ---------------------------------------------------------------------------


def test_create_with_secret_stores_the_key_in_the_vault():
    """
    **Feature: audit ORC-29**
    **Property: a create that supplies the shared secret stores it in
    the secrets vault under the integration's reference, and the
    reference resolves back to the key.**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    resolved = configuration_service.resolve_shared_secret(
        db_session=session, secret_ref=view.secret_ref,
    )
    testbase.assert_equal(resolved, SHARED_KEY.encode("utf-8"))
    return


def test_create_with_secret_persists_only_a_vault_reference():
    """
    **Feature: audit ORC-29**
    **Property: the configuration row stores the vault reference
    webhooks.in.<provider>.<hook>.<webhook_id>.secret, never the key.**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    row = (
        session.query(WebhookConfiguration)
        .filter(WebhookConfiguration.webhook_id == view.webhook_id)
        .first()
    )
    expected_ref = "webhooks.in.{}.{}.{}.secret".format(
        PROVIDER, HOOK_NAME, view.webhook_id,
    )
    testbase.assert_equal(row.secret_ref, expected_ref)
    return


def test_create_stores_the_vault_secret_in_the_project_scope():
    """
    **Feature: audit ORC-29**
    **Property: the stored vault secret is PROJECT-scoped to the
    integration's project.**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    record = (
        session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == view.secret_ref)
        .first()
    )
    testbase.assert_equal(record.scope_kind, SecretScopeKind.PROJECT)
    testbase.assert_equal(str(record.scope_ref), project_id)
    return


def test_create_route_response_never_contains_the_secret():
    """
    **Feature: audit ORC-29**
    **Property: POST /webhooks/in/integrations answers 201 and the
    response body does not contain the shared secret.**
    """
    session, admin, project_id = _prepare()
    response = _create_via_route(
        session=session,
        principal=admin,
        body={
            "project_id": project_id,
            "provider": PROVIDER,
            "hook_name": HOOK_NAME,
            "secret": SHARED_KEY,
        },
    )
    testbase.assert_equal(response.status_code, 201)
    testbase.assert_equal(SHARED_KEY in _body_text(response), False)
    return


def test_list_route_response_never_contains_the_secret():
    """
    **Feature: audit ORC-29**
    **Property: GET /webhooks/in/integrations lists the integration
    without its shared secret.**
    """
    session, admin, project_id = _prepare()
    _create_with_secret(session=session, principal=admin, project_id=project_id)
    response = _list_via_route(session=session, principal=admin, project_id=project_id)
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(SHARED_KEY in _body_text(response), False)
    return


def test_list_route_reports_the_vault_reference():
    """
    **Feature: audit ORC-29**
    **Property: the listed integration carries its vault reference and
    secret_configured=true.**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    response = _list_via_route(session=session, principal=admin, project_id=project_id)
    item = json.loads(_body_text(response))["items"][0]
    testbase.assert_equal(
        (item["secret_ref"], item["secret_configured"]),
        (view.secret_ref, True),
    )
    return


def test_list_route_never_echoes_a_value_that_is_not_a_vault_reference():
    """
    **Feature: audit ORC-29**
    **Property: a configuration whose secret_ref names no vault secret
    (for example a row written with a literal key) lists with
    secret_ref null and secret_configured false.**
    """
    session, admin, project_id = _prepare()
    configuration_service.create_webhook(
        db_session=session,
        project_id=project_id,
        provider=PROVIDER,
        hook_name=HOOK_NAME,
        secret_ref="literal-hmac-key-from-an-old-row",
    )
    response = _list_via_route(session=session, principal=admin, project_id=project_id)
    item = json.loads(_body_text(response))["items"][0]
    testbase.assert_equal(
        (item["secret_ref"], item["secret_configured"]),
        (None, False),
    )
    return


# ---------------------------------------------------------------------------
# Create: validation + authorization
# ---------------------------------------------------------------------------


def test_create_route_rejects_a_secret_ref_that_names_no_vault_secret():
    """
    **Feature: audit ORC-29**
    **Property: binding a secret_ref that is not a vault secret answers
    422 and creates nothing.**
    """
    session, admin, project_id = _prepare()
    response = _create_via_route(
        session=session,
        principal=admin,
        body={
            "project_id": project_id,
            "provider": PROVIDER,
            "hook_name": HOOK_NAME,
            "secret_ref": "just-a-literal-key",
        },
    )
    count = session.query(WebhookConfiguration).count()
    testbase.assert_equal((response.status_code, count), (422, 0))
    return


def test_create_route_binds_an_existing_readable_vault_secret():
    """
    **Feature: audit ORC-29**
    **Property: binding an existing vault secret the caller can read
    answers 201 and persists that reference.**
    """
    session, admin, project_id = _prepare()
    secrets_service.put_secret(
        db_session=session,
        principal=admin,
        secret_ref="org:shared.github.hook",
        plaintext=SecretBytes(b"shared-org-key"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.ORG,
    )
    response = _create_via_route(
        session=session,
        principal=admin,
        body={
            "project_id": project_id,
            "provider": PROVIDER,
            "hook_name": HOOK_NAME,
            "secret_ref": "org:shared.github.hook",
        },
    )
    body = json.loads(_body_text(response))
    testbase.assert_equal(
        (response.status_code, body["secret_ref"]),
        (201, "org:shared.github.hook"),
    )
    return


def test_create_route_forbids_binding_a_vault_secret_the_caller_cannot_read():
    """
    **Feature: audit ORC-29**
    **Property: a caller without read access to the named vault secret
    gets 403 and nothing is created.**
    """
    session, admin, project_id = _prepare()
    secrets_service.put_secret(
        db_session=session,
        principal=admin,
        secret_ref="org:admins.only",
        plaintext=SecretBytes(b"admin-key"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.ORG,
    )
    outsider = _principal(str(uuidmod.uuid4()))
    # The routes and the vault share one rbac_evaluator module; the
    # outsider holds only system:webhooks.write.
    perm_patch = _patch_only_webhooks_write()
    try:
        response = _create_via_route(
            session=session,
            principal=outsider,
            body={
                "project_id": project_id,
                "provider": PROVIDER,
                "hook_name": HOOK_NAME,
                "secret_ref": "org:admins.only",
            },
        )
    finally:
        perm_patch.deactivate()
    count = session.query(WebhookConfiguration).count()
    testbase.assert_equal((response.status_code, count), (403, 0))
    return


def test_create_route_without_vault_write_access_is_forbidden_and_stores_nothing():
    """
    **Feature: audit ORC-29**
    **Property: a caller who may write webhooks but not the project's
    secrets gets 403; neither a configuration nor a vault secret is
    left behind.**
    """
    session, _admin, project_id = _prepare()
    writer = _principal(str(uuidmod.uuid4()))
    perm_patch = _patch_only_webhooks_write()
    try:
        response = _create_via_route(
            session=session,
            principal=writer,
            body={
                "project_id": project_id,
                "provider": PROVIDER,
                "hook_name": HOOK_NAME,
                "secret": SHARED_KEY,
            },
        )
    finally:
        perm_patch.deactivate()
    configs = session.query(WebhookConfiguration).count()
    vault_rows = (
        session.query(SecretRecord)
        .filter(SecretRecord.secret_ref.like("webhooks.in.%"))
        .count()
    )
    testbase.assert_equal((response.status_code, configs, vault_rows), (403, 0, 0))
    return


def test_create_route_rejects_both_secret_and_secret_ref():
    """
    **Feature: audit ORC-29**
    **Property: supplying both 'secret' and 'secret_ref' answers 422.**
    """
    session, admin, project_id = _prepare()
    response = _create_via_route(
        session=session,
        principal=admin,
        body={
            "project_id": project_id,
            "provider": PROVIDER,
            "hook_name": HOOK_NAME,
            "secret": SHARED_KEY,
            "secret_ref": "org:whatever",
        },
    )
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_route_requires_a_secret():
    """
    **Feature: audit ORC-29**
    **Property: a create with neither 'secret' nor 'secret_ref'
    answers 422 naming the missing 'secret' field.**
    """
    session, admin, project_id = _prepare()
    response = _create_via_route(
        session=session,
        principal=admin,
        body={
            "project_id": project_id,
            "provider": PROVIDER,
            "hook_name": HOOK_NAME,
        },
    )
    body = json.loads(_body_text(response))
    testbase.assert_equal(
        (response.status_code, body.get("missing_fields")),
        (422, ["secret"]),
    )
    return


def test_failed_create_removes_the_vault_secret_it_stored():
    """
    **Feature: audit ORC-29**
    **Property: when the configuration row cannot be written after
    the secret was stored, the stored vault secret is removed.**
    """
    session, admin, project_id = _prepare()
    create_patch = create_module_patch(configuration_service, "create_webhook")
    create_mock = create_patch.activate()

    def _explode(**kwargs: Any) -> Any:
        raise RuntimeError("row write failed")

    create_mock.configure(side_effect=_explode)
    raised = False
    try:
        try:
            _create_with_secret(session=session, principal=admin, project_id=project_id)
        except RuntimeError:
            raised = True
    finally:
        create_patch.deactivate()
    vault_rows = (
        session.query(SecretRecord)
        .filter(SecretRecord.secret_ref.like("webhooks.in.%"))
        .count()
    )
    testbase.assert_equal((raised, vault_rows), (True, 0))
    return


# ---------------------------------------------------------------------------
# Receiver: HMAC verification with the vault-resolved key
# ---------------------------------------------------------------------------


def test_receiver_accepts_a_delivery_signed_with_the_shared_secret():
    """
    **Feature: audit ORC-29 / 8-webhooks-in**
    **Property: a delivery signed with the shared secret stored in the
    vault is accepted (202).**
    """
    session, admin, project_id = _prepare()
    _create_with_secret(session=session, principal=admin, project_id=project_id)
    response = _receive_via_route(
        session=session,
        body=json.dumps({"event": "push"}).encode("utf-8"),
        key=SHARED_KEY.encode("utf-8"),
        delivery_id="orc29-delivery-1",
    )
    testbase.assert_equal(response.status_code, 202)
    return


def test_receiver_rejects_a_delivery_signed_with_the_reference_string():
    """
    **Feature: audit ORC-29 / 8-webhooks-in**
    **Property: the stored reference is not the key -- a delivery
    signed with the secret_ref string is rejected (401).**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    response = _receive_via_route(
        session=session,
        body=json.dumps({"event": "push"}).encode("utf-8"),
        key=view.secret_ref.encode("utf-8"),
        delivery_id="orc29-delivery-2",
    )
    testbase.assert_equal(response.status_code, 401)
    return


def test_receiver_answers_503_when_the_vault_secret_is_gone():
    """
    **Feature: audit ORC-29 / 8-webhooks-in**
    **Property: when the integration's vault secret no longer exists
    the receiver answers 503 secret_unavailable instead of verifying
    against anything else.**
    """
    session, admin, project_id = _prepare()
    view = _create_with_secret(session=session, principal=admin, project_id=project_id)
    secrets_service.delete_secret(
        db_session=session,
        principal=admin,
        secret_ref=view.secret_ref,
        aspects=build_default_aspects(),
    )
    response = _receive_via_route(
        session=session,
        body=json.dumps({"event": "push"}).encode("utf-8"),
        key=SHARED_KEY.encode("utf-8"),
        delivery_id="orc29-delivery-3",
    )
    body = json.loads(_body_text(response))
    testbase.assert_equal(
        (response.status_code, body["reason"]),
        (503, "secret_unavailable"),
    )
    return


def test_receiver_passes_the_vault_resolved_key_to_the_dispatcher():
    """
    **Feature: audit ORC-29 / 8-webhooks-in**
    **Property: the dispatcher receives the key resolved from the vault,
    not the configuration's secret_ref string.**
    """
    session, admin, project_id = _prepare()
    _create_with_secret(session=session, principal=admin, project_id=project_id)
    captured: Dict[str, Any] = {}
    disp_patch = create_module_patch(webhooks_in_routes, "dispatch_inbound_webhook")
    disp_mock = disp_patch.activate()

    def _capture(**kwargs: Any) -> Any:
        captured["shared_secret"] = kwargs.get("shared_secret")
        from ccai.pychestrate.webservice.webhooks_in.dispatcher import (
            WebhookDispatchResult,
        )
        rtnval = WebhookDispatchResult(
            status="dispatched",
            request_id="req-orc29",
            provider=PROVIDER,
            hook_name=HOOK_NAME,
            delivery_id="d",
            domain_event_count=1,
            rejection=None,
            matched_signature_header="X-Pychestrate-Signature",
        )
        return rtnval

    disp_mock.configure(side_effect=_capture)
    try:
        _receive_via_route(
            session=session,
            body=b"{}",
            key=b"irrelevant",
            delivery_id="orc29-delivery-4",
        )
    finally:
        disp_patch.deactivate()
    testbase.assert_equal(captured.get("shared_secret"), SHARED_KEY.encode("utf-8"))
    return
