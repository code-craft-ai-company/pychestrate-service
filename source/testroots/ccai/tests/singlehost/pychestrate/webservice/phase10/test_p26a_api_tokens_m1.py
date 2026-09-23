"""
.. module:: test_p26a_api_tokens_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for machine identity -- API tokens and service
               accounts (audit finding ORG-F02).

.. moduleauthor:: Code Craft AI LLC

Before this change the only way to authenticate against
``/api/v1/*`` or ``/mcp/*`` was the browser's session cookie, so CI,
the ``pyc`` CLI, and MCP agents had to scrape the sign-in form.

Coverage (each against a real in-memory database):

* :mod:`security.auth.api_tokens.service` -- issuing (secret shown
  once, only its digest stored, every token expires), validation,
  authentication (unknown / revoked / expired / inactive account),
  last-used time, audit records for creation, use and revocation,
  owner scoping, service accounts, and principal-bound RBAC.
* :class:`middleware_webworks.PychestrateSessionMiddleware` -- a
  ``Bearer pyc_...`` token (or ``X-Pychestrate-Api-Key``) becomes the
  request principal; a bad token leaves the request anonymous (401)
  without falling back to the cookie; a read-only token cannot write;
  anonymous default-deny still holds.
* :mod:`security.auth.restapi.v1.api_tokens_routes` -- route
  permissions, token issuance (201, no-store, refused to token
  callers), ``/me``, owner scoping, service-account endpoints.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import sessionmaker

from ccai import testbase
from ccai.webworks.routing.request import Request

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.audit.bus_subscriber import (
    wire_bus_subscribers as wire_audit_subscribers,
)
from ccai.pychestrate.webservice.audit.models import AuditRecord
from ccai.pychestrate.webservice.identity.users import user_service
from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from ccai.pychestrate.webservice.middleware_webworks import (
    PychestrateSessionMiddleware,
    default_resolve_api_token,
    extract_api_token,
    install_pychestrate_session_middleware,
)
from ccai.pychestrate.webservice.security.auth.anonymous_access import (
    is_anonymous_request_permitted,
)
from ccai.pychestrate.webservice.security.auth.api_tokens import service as token_service
from ccai.pychestrate.webservice.security.auth.api_tokens.exceptions import (
    ApiTokenNotFoundError,
    ApiTokenRejectedError,
    ApiTokenValidationError,
)
from ccai.pychestrate.webservice.security.auth.api_tokens.models import AuthApiToken
from ccai.pychestrate.webservice.security.auth.models import (
    AuthLocalCredentials,
    AuthProviderKind,
)
from ccai.pychestrate.webservice.security.auth.restapi.v1 import api_tokens_routes
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
from ccai.pychestrate.webservice.security.rbac import cache as rbac_cache
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)
from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
)


VERSION_PREFIX = "/api/v1"
FIXED_NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_database() -> Tuple[Any, Any]:
    """
        Reset the runtime, build an in-memory database, and wire the
        audit subscribers so entity events land in ``audit_records``.
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()
    wire_audit_subscribers(session_factory=sessionmaker(bind=engine))
    rtnval = (engine, session)
    return rtnval


def _make_user(*, session: Any, login_name: str = "alice") -> IdentityUser:
    user = user_service.create_user(
        db_session=session,
        login_name=login_name,
        primary_email="{}@example.test".format(login_name),
        display_name=login_name.title(),
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )
    return user


def _issue(
        *,
        session: Any,
        user: Any,
        scope: Optional[str] = None,
        lifetime_days: Optional[int] = None,
        now: datetime = FIXED_NOW
    ) -> Any:
    rtnval = token_service.create_api_token(
        db_session=session,
        user_id=str(user.user_id),
        name="ci",
        lifetime_days=lifetime_days,
        scope=scope,
        actor_user_id=str(user.user_id),
        now=now,
    )
    return rtnval


def _authenticate(*, session: Any, token: str, now: datetime = FIXED_NOW) -> Any:
    rtnval = token_service.authenticate_api_token(
        db_session=session,
        token=token,
        now=now,
        request_method="GET",
        request_path="/api/v1/projects",
    )
    return rtnval


def _audit_kinds(*, session: Any) -> List[str]:
    rows = session.query(AuditRecord).order_by(AuditRecord.sequence_number).all()
    rtnval = [row.kind for row in rows]
    return rtnval


def _rejection_reason(*, session: Any, token: str, now: datetime = FIXED_NOW) -> Optional[str]:
    try:
        _authenticate(session=session, token=token, now=now)
    except ApiTokenRejectedError as xcpt:
        return xcpt.reason
    return None


def _bind_system_admin(*, session: Any, user_id: str) -> None:
    role = RbacRole(
        role_id=new_uuid(),
        role_name="system-admin",
        source=RoleSource.BUILTIN,
        source_name="CorePermissionExtension",
        description="",
    )
    session.add(role)
    session.flush()
    session.add(
        RbacRoleBinding(
            binding_id=new_uuid(),
            role_id=role.role_id,
            principal_kind=PrincipalKind.USER,
            principal_id=user_id,
            scope_kind=BindingScope.SYSTEM,
            scope_id=None,
            inherits_into_project=False,
            created_by=None,
        )
    )
    session.commit()
    rbac_cache.reset_for_testing()
    return


def _session_principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id=user_id,
        session_id="cookie-session",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def _body(response: Any) -> Dict[str, Any]:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


# ===========================================================================
# Issuing
# ===========================================================================


def test_issued_token_carries_the_pyc_prefix():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: an issued token is a pyc_-prefixed string with 256
    bits of randomness (43 URL-safe characters after the prefix).**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        testbase.assert_equal(
            (issued.token.startswith("pyc_"), len(issued.token) - len("pyc_")),
            (True, 43),
        )
    finally:
        session.close()
    return


def test_only_the_token_digest_is_stored():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: the stored row holds the SHA-256 digest of the token
    and no column holds the token itself.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        row = session.query(AuthApiToken).one()
        values = [str(getattr(row, column.name)) for column in AuthApiToken.__table__.columns]
        testbase.assert_equal(
            (row.token_sha256 == hashlib.sha256(issued.token.encode("utf-8")).hexdigest(),
             issued.token in values),
            (True, False),
        )
    finally:
        session.close()
    return


def test_token_defaults_to_ninety_days_and_read_write():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: without a lifetime or scope the token expires after
    90 days and is read-write.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        testbase.assert_equal(
            (issued.view.expires_at, issued.view.scope),
            (FIXED_NOW + timedelta(days=90), "read-write"),
        )
    finally:
        session.close()
    return


def test_token_lifetime_outside_one_to_366_days_is_refused():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: every token expires, within 1-366 days; any other
    lifetime (0, 367, text, a boolean) is a validation error.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        outcomes: Dict[str, bool] = {}
        for lifetime_days in (0, 367, "soon", True):
            raised = False
            try:
                _issue(session=session, user=user, lifetime_days=lifetime_days)
            except ApiTokenValidationError:
                raised = True
            outcomes[repr(lifetime_days)] = raised
        testbase.assert_equal(
            outcomes, {"0": True, "367": True, "'soon'": True, "True": True}
        )
    finally:
        session.close()
    return


def test_token_with_an_unknown_scope_is_refused():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: scope must be read-write or read-only.**
    """
    _engine, session = _fresh_database()
    try:
        raised = False
        try:
            _issue(session=session, user=_make_user(session=session), scope="admin")
        except ApiTokenValidationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_token_without_a_name_is_refused():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a blank token name is a validation error.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        raised = False
        try:
            token_service.create_api_token(
                db_session=session, user_id=str(user.user_id), name="   ",
                lifetime_days=None, scope=None, actor_user_id=None, now=FIXED_NOW,
            )
        except ApiTokenValidationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_deactivated_account_cannot_be_issued_a_token():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a token cannot be issued for an account that is not
    active.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        user.status = UserStatus.DEACTIVATED
        session.commit()
        raised = False
        try:
            _issue(session=session, user=user)
        except ApiTokenValidationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_issuing_a_token_is_audited():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: issuing a token writes an audit.api_token.created
    record naming the token and never its secret.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        record = (
            session.query(AuditRecord)
            .filter(AuditRecord.kind == "audit.api_token.created")
            .one()
        )
        testbase.assert_equal(
            (record.target_ref, issued.token in json.dumps(record.payload_json)),
            ("api_token:{}".format(issued.view.token_id), False),
        )
    finally:
        session.close()
    return


# ===========================================================================
# Authenticating
# ===========================================================================


def test_token_authenticates_as_its_owner():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a valid token resolves to a principal whose user_id
    is the token's owner, with the token's id, name and scope.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        issued = _issue(session=session, user=user)
        principal = _authenticate(session=session, token=issued.token)
        testbase.assert_equal(
            (principal.user_id, principal.token_id, principal.token_name, principal.token_scope),
            (str(user.user_id), issued.view.token_id, "ci", "read-write"),
        )
    finally:
        session.close()
    return


def test_unknown_token_is_rejected():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a well-formed token that was never issued is rejected
    (reason unknown).**
    """
    _engine, session = _fresh_database()
    try:
        _issue(session=session, user=_make_user(session=session))
        testbase.assert_equal(
            _rejection_reason(session=session, token="pyc_" + "A" * 43), "unknown"
        )
    finally:
        session.close()
    return


def test_revoked_token_is_rejected():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a revoked token no longer authenticates.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        issued = _issue(session=session, user=user)
        token_service.revoke_api_token(
            db_session=session, token_id=issued.view.token_id,
            actor_user_id=str(user.user_id), now=FIXED_NOW,
        )
        testbase.assert_equal(_rejection_reason(session=session, token=issued.token), "revoked")
    finally:
        session.close()
    return


def test_expired_token_is_rejected():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a token is rejected once its expiry has passed.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session), lifetime_days=7)
        testbase.assert_equal(
            _rejection_reason(
                session=session, token=issued.token, now=FIXED_NOW + timedelta(days=7, seconds=1)
            ),
            "expired",
        )
    finally:
        session.close()
    return


def test_token_of_a_deactivated_account_is_rejected():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: deactivating the account stops its tokens working.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        issued = _issue(session=session, user=user)
        user.status = UserStatus.DEACTIVATED
        session.commit()
        testbase.assert_equal(
            _rejection_reason(session=session, token=issued.token), "account_inactive"
        )
    finally:
        session.close()
    return


def test_authentication_records_the_last_used_time():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a successful authentication stores last_used_at.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        used_at = FIXED_NOW + timedelta(minutes=5)
        _authenticate(session=session, token=issued.token, now=used_at)
        view = token_service.read_api_token(db_session=session, token_id=issued.view.token_id, now=used_at)
        testbase.assert_equal(view.last_used_at, used_at)
    finally:
        session.close()
    return


def test_first_use_of_a_token_is_audited():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: the first request a token authenticates writes an
    audit.api_token.used record with the method and path.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        _authenticate(session=session, token=issued.token)
        record = (
            session.query(AuditRecord)
            .filter(AuditRecord.kind == "audit.api_token.used")
            .one()
        )
        testbase.assert_equal(
            (record.payload_json["method"], record.payload_json["path"]),
            ("GET", "/api/v1/projects"),
        )
    finally:
        session.close()
    return


def test_use_audit_is_throttled_to_once_an_hour():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: requests within an hour of the recorded use add no
    audit record; the first request after the hour adds one.**
    """
    _engine, session = _fresh_database()
    try:
        issued = _issue(session=session, user=_make_user(session=session))
        for minutes in (0, 2, 30, 59, 61):
            _authenticate(session=session, token=issued.token, now=FIXED_NOW + timedelta(minutes=minutes))
        kinds = _audit_kinds(session=session)
        testbase.assert_equal(kinds.count("audit.api_token.used"), 2)
    finally:
        session.close()
    return


def test_revoking_a_token_is_audited():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: revoking a token writes one audit.api_token.revoked
    record; revoking it again writes nothing.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        issued = _issue(session=session, user=user)
        for _attempt in range(2):
            token_service.revoke_api_token(
                db_session=session, token_id=issued.view.token_id,
                actor_user_id=str(user.user_id), now=FIXED_NOW,
            )
        testbase.assert_equal(_audit_kinds(session=session).count("audit.api_token.revoked"), 1)
    finally:
        session.close()
    return


def test_owner_scoped_revoke_cannot_touch_another_users_token():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: self-service revocation of someone else's token reads
    as not found and leaves the token working.**
    """
    _engine, session = _fresh_database()
    try:
        alice = _make_user(session=session, login_name="alice")
        mallory = _make_user(session=session, login_name="mallory")
        issued = _issue(session=session, user=alice)
        raised = False
        try:
            token_service.revoke_api_token(
                db_session=session, token_id=issued.view.token_id,
                actor_user_id=str(mallory.user_id), owner_user_id=str(mallory.user_id),
                now=FIXED_NOW,
            )
        except ApiTokenNotFoundError:
            raised = True
        still_works = _authenticate(session=session, token=issued.token).user_id == str(alice.user_id)
        testbase.assert_equal((raised, still_works), (True, True))
    finally:
        session.close()
    return


def test_listing_a_users_tokens_excludes_other_users():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: list_api_tokens(user_id=...) returns only that user's
    tokens.**
    """
    _engine, session = _fresh_database()
    try:
        alice = _make_user(session=session, login_name="alice")
        bob = _make_user(session=session, login_name="bob")
        _issue(session=session, user=alice)
        _issue(session=session, user=bob)
        views = token_service.list_api_tokens(db_session=session, user_id=str(alice.user_id))
        testbase.assert_equal([view.login_name for view in views], ["alice"])
    finally:
        session.close()
    return


def test_token_grants_no_more_than_its_principal_holds():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a token principal is evaluated with its user's RBAC --
    denied a permission the user lacks, allowed once the user holds
    it.**
    """
    _engine, session = _fresh_database()
    try:
        user = _make_user(session=session)
        issued = _issue(session=session, user=user)
        principal = _authenticate(session=session, token=issued.token)
        before = rbac_evaluator.check_permission(
            db_session=session, principal=principal,
            permission_key="system:projects.read", now=FIXED_NOW,
        ).allowed
        _bind_system_admin(session=session, user_id=str(user.user_id))
        after = rbac_evaluator.check_permission(
            db_session=session, principal=principal,
            permission_key="system:projects.read", now=FIXED_NOW,
        ).allowed
        testbase.assert_equal((before, after), (False, True))
    finally:
        session.close()
    return


# ===========================================================================
# Service accounts
# ===========================================================================


def test_service_account_is_an_identity_user_without_a_password():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: a service account is an active identity user marked
    provisioning_source=service_account, with an undeliverable
    .invalid e-mail and no local credentials (it cannot sign in).**
    """
    _engine, session = _fresh_database()
    try:
        user = token_service.create_service_account(
            db_session=session, login_name="CI-Nightly", display_name="", actor_user_id=None,
        )
        credentials = (
            session.query(AuthLocalCredentials)
            .filter(AuthLocalCredentials.user_id == user.user_id)
            .count()
        )
        testbase.assert_equal(
            (user.login_name, user.provisioning_source, user.primary_email, credentials),
            ("ci-nightly", "service_account", "ci-nightly@service-accounts.invalid", 0),
        )
    finally:
        session.close()
    return


def test_service_account_login_name_is_validated():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: a login name must be 2-63 lower-case letters, digits,
    '.', '_' or '-', starting with a letter or digit; every malformed
    name is a validation error.**
    """
    _engine, session = _fresh_database()
    try:
        outcomes: Dict[str, bool] = {}
        for login_name in ("", "x", "has space", "-leading-dash", "a" * 64, None):
            raised = False
            try:
                token_service.create_service_account(
                    db_session=session, login_name=login_name, display_name="x", actor_user_id=None,
                )
            except ApiTokenValidationError:
                raised = True
            outcomes[repr(login_name)] = raised
        testbase.assert_equal(outcomes, {name: True for name in outcomes})
    finally:
        session.close()
    return


def test_duplicate_service_account_name_is_a_validation_error():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: creating a service account with a taken login name is
    a validation error, not a crash.**
    """
    _engine, session = _fresh_database()
    try:
        token_service.create_service_account(
            db_session=session, login_name="ci", display_name="", actor_user_id=None,
        )
        raised = False
        try:
            token_service.create_service_account(
                db_session=session, login_name="ci", display_name="", actor_user_id=None,
            )
        except ApiTokenValidationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_service_account_listing_counts_working_tokens():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: list_service_accounts reports each account's count of
    tokens that still authenticate (revoked ones excluded).**
    """
    _engine, session = _fresh_database()
    try:
        account = token_service.create_service_account(
            db_session=session, login_name="ci", display_name="CI", actor_user_id=None,
        )
        _issue(session=session, user=account)
        revoked = _issue(session=session, user=account)
        token_service.revoke_api_token(
            db_session=session, token_id=revoked.view.token_id, actor_user_id=None, now=FIXED_NOW,
        )
        views = token_service.list_service_accounts(db_session=session, now=FIXED_NOW)
        testbase.assert_equal(
            [(view.login_name, view.active_token_count) for view in views], [("ci", 1)]
        )
    finally:
        session.close()
    return


# ===========================================================================
# Middleware
# ===========================================================================


class _RecordingHandler:
    """
        Downstream handler stand-in: records the principal it saw.
    """

    def __init__(self) -> None:
        self.principals: List[Any] = []
        return

    def __call__(self, request: Any) -> str:
        self.principals.append(getattr(request, "auth_principal", None))
        return "handler-ran"


def _middleware(
        *,
        session: Any,
        cookie_principal: Optional[Any] = None
    ) -> PychestrateSessionMiddleware:
    """
        Build the middleware as production does (anonymous policy and
        token resolver), over the test database. A request carrying
        cookie ``pychestrate_session=good`` resolves to
        ``cookie_principal``.
    """

    def _resolve_cookie(db_session: Any, session_id: str, now: datetime) -> Optional[Any]:
        if session_id == "good":
            return cookie_principal
        return None

    rtnval = PychestrateSessionMiddleware(
        open_session=lambda: session,
        resolve_actor=_resolve_cookie,
        cookie_name="pychestrate_session",
        path_prefixes=("/api/v1/", "/mcp/"),
        fallback_cookie_resolvers=[],
        clock=lambda: FIXED_NOW,
        anonymous_access_policy=is_anonymous_request_permitted,
        resolve_api_token=default_resolve_api_token,
    )
    return rtnval


def _request(
        *,
        method: str = "GET",
        path: str = "/api/v1/projects",
        headers: Optional[Dict[str, str]] = None
    ) -> Request:
    rtnval = Request(method=method, path=path, headers=headers or {})
    return rtnval


def test_bearer_token_becomes_the_request_principal():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: Authorization: Bearer <token> authenticates the
    request as the token's owner.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    user_id = str(user.user_id)
    issued = _issue(session=session, user=user)
    handler = _RecordingHandler()
    _middleware(session=session)(
        _request(headers={"Authorization": "Bearer " + issued.token}), handler
    )
    testbase.assert_equal(handler.principals[0].user_id, user_id)
    return


def test_api_key_header_is_accepted():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: the X-Pychestrate-Api-Key header the OpenAPI document
    declares authenticates like a bearer token.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    user_id = str(user.user_id)
    issued = _issue(session=session, user=user)
    handler = _RecordingHandler()
    _middleware(session=session)(
        _request(headers={"X-Pychestrate-Api-Key": issued.token}), handler
    )
    testbase.assert_equal(handler.principals[0].user_id, user_id)
    return


def test_bearer_token_authenticates_the_mcp_endpoint():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a bearer token authenticates /mcp/* requests too.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    user_id = str(user.user_id)
    issued = _issue(session=session, user=user)
    handler = _RecordingHandler()
    _middleware(session=session)(
        _request(method="POST", path="/mcp/1/service",
                 headers={"Authorization": "Bearer " + issued.token}),
        handler,
    )
    testbase.assert_equal(handler.principals[0].user_id, user_id)
    return


def test_rejected_token_is_answered_401_with_a_token_specific_detail():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: an unknown token leaves the request anonymous, so the
    default-deny policy answers 401 naming the token problem and the
    handler never runs.**
    """
    _engine, session = _fresh_database()
    handler = _RecordingHandler()
    response = _middleware(session=session)(
        _request(headers={"Authorization": "Bearer pyc_" + "B" * 43}), handler
    )
    testbase.assert_equal(
        (response.status_code, _body(response)["detail"], len(handler.principals)),
        (401, "The API token is invalid, expired, or revoked.", 0),
    )
    return


def test_rejected_token_does_not_fall_back_to_the_cookie():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a request presenting a bad token is refused even when
    it also carries a valid session cookie -- an explicit credential
    never silently acts as the browser's user.**
    """
    _engine, session = _fresh_database()
    handler = _RecordingHandler()
    middleware = _middleware(session=session, cookie_principal=_session_principal(new_uuid()))
    response = middleware(
        _request(headers={
            "Authorization": "Bearer pyc_" + "C" * 43,
            "Cookie": "pychestrate_session=good",
        }),
        handler,
    )
    testbase.assert_equal((response.status_code, len(handler.principals)), (401, 0))
    return


def test_non_pyc_bearer_value_is_left_to_the_cookie():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a bearer value without the pyc_ prefix is not treated
    as an API token; the session cookie still authenticates.**
    """
    _engine, session = _fresh_database()
    cookie_principal = _session_principal(new_uuid())
    handler = _RecordingHandler()
    _middleware(session=session, cookie_principal=cookie_principal)(
        _request(headers={
            "Authorization": "Bearer eyJhbGciOi.some.jwt",
            "Cookie": "pychestrate_session=good",
        }),
        handler,
    )
    testbase.assert_equal(handler.principals[0] is cookie_principal, True)
    return


def test_read_only_token_cannot_write():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a read-only token used with POST is answered 403
    before the handler runs.**
    """
    _engine, session = _fresh_database()
    issued = _issue(session=session, user=_make_user(session=session), scope="read-only")
    handler = _RecordingHandler()
    response = _middleware(session=session)(
        _request(method="POST", headers={"Authorization": "Bearer " + issued.token}),
        handler,
    )
    testbase.assert_equal((response.status_code, len(handler.principals)), (403, 0))
    return


def test_read_only_token_can_read():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a read-only token used with GET reaches the handler.**
    """
    _engine, session = _fresh_database()
    issued = _issue(session=session, user=_make_user(session=session), scope="read-only")
    handler = _RecordingHandler()
    _middleware(session=session)(
        _request(method="GET", headers={"Authorization": "Bearer " + issued.token}),
        handler,
    )
    testbase.assert_equal(len(handler.principals), 1)
    return


def test_read_only_token_may_post_to_the_mcp_endpoint():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a read-only token's POST to the MCP endpoint reaches the
    handler (MCP carries reads over POST and refuses write tools to
    read-only tokens itself), while a POST elsewhere is still refused.**
    """
    _engine, session = _fresh_database()
    issued = _issue(session=session, user=_make_user(session=session), scope="read-only")
    headers = {"Authorization": "Bearer " + issued.token}
    mcp_handler = _RecordingHandler()
    _middleware(session=session)(_request(method="POST", path="/mcp/1/service", headers=headers), mcp_handler)
    rest_handler = _RecordingHandler()
    rest = _middleware(session=session)(_request(method="POST", headers=headers), rest_handler)
    testbase.assert_equal((len(mcp_handler.principals), rest.status_code), (1, 403))
    return


def test_request_without_credentials_is_still_refused():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: with the token resolver installed, a request with no
    token and no cookie is still refused by the default-deny policy
    with the generic 401.**
    """
    _engine, session = _fresh_database()
    handler = _RecordingHandler()
    response = _middleware(session=session)(_request(), handler)
    testbase.assert_equal(
        (response.status_code, _body(response)["detail"]), (401, "Authentication required.")
    )
    return


def test_extract_api_token_matches_the_bearer_scheme_case_insensitively():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: 'bearer' in any case introduces a token.**
    """
    request = _request(headers={"Authorization": "BEARER pyc_abc"})
    testbase.assert_equal(extract_api_token(request), "pyc_abc")
    return


class _FakeDispatcher:
    def __init__(self) -> None:
        self.pipeline = _FakePipeline()
        return


class _FakePipeline:
    def __init__(self) -> None:
        self.added: List[Any] = []
        return

    def add(self, middleware: Any, name: str, position: str) -> None:
        self.added.append(middleware)
        return


class _FakeApp:
    def __init__(self) -> None:
        self.dispatcher = _FakeDispatcher()
        return


def test_installer_wires_the_api_token_resolver_by_default():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: install_pychestrate_session_middleware, called as the
    production bootstrap calls it, authenticates API tokens with
    default_resolve_api_token.**
    """
    middleware = install_pychestrate_session_middleware(
        app=_FakeApp(),
        path_prefixes=("/api/v1/",),
        open_session=lambda: None,
        resolve_actor=lambda db_session, session_id, now: None,
    )
    testbase.assert_equal(middleware._resolve_api_token is default_resolve_api_token, True)
    return


# ===========================================================================
# REST routes
# ===========================================================================


def _declared_permissions() -> Dict[Tuple[str, str], Any]:
    app = make_fake_app()
    api_tokens_routes.register_api_tokens_routes(app=app, version_prefix=VERSION_PREFIX)
    rtnval: Dict[Tuple[str, str], Any] = {}
    for path, methods, handler in app.calls:
        for method in methods:
            rtnval[(method, path)] = getattr(handler, "required_permission", "<unwrapped>")
    return rtnval


def test_rest_routes_declare_their_permissions():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: self-service routes need only a signed-in principal;
    administration routes declare system:auth.* / system:users.*.**
    """
    expected = {
        ("GET", "/api/v1/me"): None,
        ("GET", "/api/v1/me/api-tokens"): None,
        ("POST", "/api/v1/me/api-tokens"): None,
        ("GET", "/api/v1/me/api-tokens/{token_id}"): None,
        ("DELETE", "/api/v1/me/api-tokens/{token_id}"): None,
        ("GET", "/api/v1/api-tokens"): "system:auth.read",
        ("DELETE", "/api/v1/api-tokens/{token_id}"): "system:auth.admin",
        ("GET", "/api/v1/service-accounts"): "system:users.read",
        ("POST", "/api/v1/service-accounts"): "system:users.write",
        ("GET", "/api/v1/service-accounts/{user_id}/api-tokens"): "system:auth.read",
        ("POST", "/api/v1/service-accounts/{user_id}/api-tokens"): "system:auth.admin",
    }
    testbase.assert_equal(_declared_permissions(), expected)
    return


def _rest_request(
        *,
        method: str,
        path: str,
        principal: Any,
        session: Any,
        body: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, str]] = None
    ) -> Request:
    raw = json.dumps(body).encode("utf-8") if body is not None else b""
    request = Request(
        method=method, path=path,
        headers={"Content-Type": "application/json"} if body is not None else {},
        body=raw,
    )
    request.auth_principal = principal
    request.db_session = session
    request.path_params = path_params or {}
    rtnval = request
    return rtnval


def test_creating_my_token_returns_the_secret_once_uncached():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: POST /api/v1/me/api-tokens from a signed-in session
    answers 201 with the pyc_ token and Cache-Control: no-store.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    response = api_tokens_routes.handle_create_my_token(
        _rest_request(
            method="POST", path="/api/v1/me/api-tokens",
            principal=_session_principal(str(user.user_id)), session=session,
            body={"name": "laptop", "expires_in_days": 30, "scope": "read-only"},
        )
    )
    body = _body(response)
    testbase.assert_equal(
        (response.status_code, body["token"][:4], body["scope"],
         response.headers.get("Cache-Control")),
        (201, "pyc_", "read-only", "no-store"),
    )
    return


def test_token_authenticated_caller_cannot_issue_tokens():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a request authenticated with an API token is refused
    (403) when it tries to issue a token, so a leaked token cannot
    mint a longer-lived successor.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    issued = _issue(session=session, user=user)
    principal = _authenticate(session=session, token=issued.token)
    response = api_tokens_routes.handle_create_my_token(
        _rest_request(
            method="POST", path="/api/v1/me/api-tokens",
            principal=principal, session=session, body={"name": "successor"},
        )
    )
    count = session.query(AuthApiToken).count()
    testbase.assert_equal((response.status_code, count), (403, 1))
    return


def test_invalid_token_request_is_a_422():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: a token request with an out-of-range lifetime answers
    422 with the validation message.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    response = api_tokens_routes.handle_create_my_token(
        _rest_request(
            method="POST", path="/api/v1/me/api-tokens",
            principal=_session_principal(str(user.user_id)), session=session,
            body={"name": "x", "expires_in_days": 1000},
        )
    )
    testbase.assert_equal(response.status_code, 422)
    return


def test_me_reports_token_authentication():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: GET /api/v1/me for a token principal names the user
    and reports method api_token with the token's name and scope.**
    """
    _engine, session = _fresh_database()
    user = _make_user(session=session)
    issued = _issue(session=session, user=user)
    principal = _authenticate(session=session, token=issued.token)
    body = _body(api_tokens_routes.handle_get_me(
        _rest_request(method="GET", path="/api/v1/me", principal=principal, session=session)
    ))
    testbase.assert_equal(
        (body["login_name"], body["account_kind"], body["authentication"]["method"],
         body["authentication"]["token_name"]),
        ("alice", "user", "api_token", "ci"),
    )
    return


def test_me_reports_a_service_account():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: GET /api/v1/me for a service account's token reports
    account_kind service_account.**
    """
    _engine, session = _fresh_database()
    account = token_service.create_service_account(
        db_session=session, login_name="ci", display_name="CI", actor_user_id=None,
    )
    issued = _issue(session=session, user=account)
    principal = _authenticate(session=session, token=issued.token)
    body = _body(api_tokens_routes.handle_get_me(
        _rest_request(method="GET", path="/api/v1/me", principal=principal, session=session)
    ))
    testbase.assert_equal(body["account_kind"], "service_account")
    return


def test_revoking_someone_elses_token_via_me_is_a_404():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: DELETE /api/v1/me/api-tokens/{id} of another user's
    token answers 404 and the token keeps working.**
    """
    _engine, session = _fresh_database()
    alice = _make_user(session=session, login_name="alice")
    bob = _make_user(session=session, login_name="bob")
    issued = _issue(session=session, user=alice)
    response = api_tokens_routes.handle_revoke_my_token(
        _rest_request(
            method="DELETE", path="/api/v1/me/api-tokens/x",
            principal=_session_principal(str(bob.user_id)), session=session,
            path_params={"token_id": issued.view.token_id},
        )
    )
    testbase.assert_equal(
        (response.status_code, _authenticate(session=session, token=issued.token).user_id),
        (404, str(alice.user_id)),
    )
    return


def test_bad_service_account_name_is_a_422():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: POST /api/v1/service-accounts with an invalid login
    name answers 422.**
    """
    _engine, session = _fresh_database()
    admin = _make_user(session=session, login_name="admin")
    response = api_tokens_routes.handle_create_service_account(
        _rest_request(
            method="POST", path="/api/v1/service-accounts",
            principal=_session_principal(str(admin.user_id)), session=session,
            body={"login_name": "Not Valid!"},
        )
    )
    testbase.assert_equal(response.status_code, 422)
    return


def test_service_account_token_endpoint_refuses_a_person():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: POST /api/v1/service-accounts/{id}/api-tokens for a
    person's user id answers 404 -- administrators cannot mint tokens
    that act as other people.**
    """
    _engine, session = _fresh_database()
    admin = _make_user(session=session, login_name="admin")
    person = _make_user(session=session, login_name="person")
    response = api_tokens_routes.handle_create_service_account_token(
        _rest_request(
            method="POST", path="/api/v1/service-accounts/x/api-tokens",
            principal=_session_principal(str(admin.user_id)), session=session,
            body={"name": "impersonate"},
            path_params={"user_id": str(person.user_id)},
        )
    )
    testbase.assert_equal(
        (response.status_code, session.query(AuthApiToken).count()), (404, 0)
    )
    return


def test_service_account_token_is_issued_by_an_administrator():
    """
    **Feature: service accounts (ORG-F02)**
    **Property: POST /api/v1/service-accounts/{id}/api-tokens issues a
    token that authenticates as the service account and records the
    administrator as its creator.**
    """
    _engine, session = _fresh_database()
    admin = _make_user(session=session, login_name="admin")
    account = token_service.create_service_account(
        db_session=session, login_name="ci", display_name="CI", actor_user_id=None,
    )
    response = api_tokens_routes.handle_create_service_account_token(
        _rest_request(
            method="POST", path="/api/v1/service-accounts/x/api-tokens",
            principal=_session_principal(str(admin.user_id)), session=session,
            body={"name": "nightly"},
            path_params={"user_id": str(account.user_id)},
        )
    )
    body = _body(response)
    principal = _authenticate(session=session, token=body["token"])
    testbase.assert_equal(
        (response.status_code, principal.user_id, body["created_by_user_id"]),
        (201, str(account.user_id), str(admin.user_id)),
    )
    return


def test_openapi_contract_documents_every_token_route():
    """
    **Feature: API tokens (ORG-F02)**
    **Property: every route register_api_tokens_routes attaches is
    described in specs/openapi/pychestrate.yaml with the same method,
    and the document declares the bearer security scheme.**
    """
    import os  # noqa: E402

    import yaml  # noqa: E402

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = here
    while not os.path.isdir(os.path.join(repo_root, "specs")) and repo_root != os.path.dirname(repo_root):
        repo_root = os.path.dirname(repo_root)
    with open(os.path.join(repo_root, "specs", "openapi", "pychestrate.yaml"), "r", encoding="utf-8") as fh:
        document = yaml.safe_load(fh)

    missing: List[str] = []
    for (method, path) in _declared_permissions().keys():
        relative = path[len(VERSION_PREFIX):]
        entry = document["paths"].get(relative, {})
        if method.lower() not in entry:
            missing.append("{} {}".format(method, relative))
    scheme = document["components"]["securitySchemes"].get("pychestrate_bearer", {})
    testbase.assert_equal(
        (missing, scheme.get("type"), scheme.get("scheme")), ([], "http", "bearer")
    )
    return
