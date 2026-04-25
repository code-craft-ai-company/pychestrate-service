"""
.. module:: test_p19b_oidc_auth_provider_m2
    :synopsis: Tests for P19b — 1-authentication M2 OidcAuthProvider.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from urllib import parse as urlparse

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (
    InboundFlowPayload,
    RedirectDescriptor,
)
from automojo.pychestrate.webservice.security.auth.factories.oidc_provider import (
    OidcAuthProvider,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthOidcState,
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    OidcCallbackError,
)
from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    JwksKey,
    encode_test_token,
)
from automojo.pychestrate.webservice.security.auth.oidc.provider_registry import (
    OidcProviderConfig,
    get_oidc_provider_config,
    list_oidc_provider_names,
    register_oidc_provider,
    reset_for_testing as reset_provider_registry,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeRawResponse,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


HS256_KEY: bytes = b"\xcd" * 32


def _key_resolver():
    def _resolver(kid):
        if kid != "kid-1":
            return None
        return JwksKey(kid="kid-1", alg="HS256", key=HS256_KEY)
    return _resolver


def _id_token(*, nonce: str, sub: str = "idp-user-7") -> str:
    # OidcAuthProvider doesn't surface a 'now' override on the
    # protocol surface, so the token has to be valid against
    # real wall-clock time.
    anchor = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT", "kid": "kid-1"}
    payload = {
        "iss": "https://idp.example.com",
        "aud": "client-pychestrate",
        "sub": sub,
        "email": "alice@example.com",
        "name": "Alice",
        "zoneinfo": "UTC",
        "exp": int((anchor + timedelta(minutes=10)).timestamp()),
        "iat": int(anchor.timestamp()),
        "nonce": nonce,
    }
    rtnval = encode_test_token(
        header=header, payload=payload, hs256_key=HS256_KEY,
    )
    return rtnval


def _token_fetcher_factory(*, id_token_provider):
    def _fetcher(request):
        return TokenExchangeRawResponse(
            status_code=200,
            payload={
                "id_token": id_token_provider(),
                "access_token": "access-bytes",
                "refresh_token": "refresh-bytes",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
    return _fetcher


def _build_config(
        *,
        session,
        provider_name: str = "okta",
        captured_nonce_box=None
    ) -> OidcProviderConfig:
    if captured_nonce_box is None:
        captured_nonce_box = []

    def _id_token_provider():
        # The state row carries the nonce we issued at begin
        # time; the row hasn't been consumed yet so we can read
        # it back to mint a matching id_token.
        if len(captured_nonce_box) > 0:
            return _id_token(nonce=captured_nonce_box[-1])
        rows = session.query(AuthOidcState).all()
        if len(rows) == 0:
            return _id_token(nonce="missing")
        return _id_token(nonce=rows[0].nonce)

    rtnval = OidcProviderConfig(
        provider_name=provider_name,
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        expected_issuer="https://idp.example.com",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        token_fetcher=_token_fetcher_factory(
            id_token_provider=_id_token_provider,
        ),
        key_resolver=_key_resolver(),
        session_factory=lambda: session,
    )
    return rtnval


def _setup(*, provider_name: str = "okta"):
    reset_provider_registry()
    _engine, session = build_in_memory_session()
    captured_nonce_box: list = []
    config = _build_config(
        session=session,
        provider_name=provider_name,
        captured_nonce_box=captured_nonce_box,
    )
    register_oidc_provider(config=config)
    return session, config, captured_nonce_box


def _begin_and_capture_nonce(
        *, session, captured_nonce_box, provider_name: str = "okta",
        redirect_target: str = "/welcome"
    ):
    redirect = OidcAuthProvider.build_begin_login_redirect(
        provider_name=provider_name, redirect_target=redirect_target,
    )
    state_row = (
        session.query(AuthOidcState)
        .filter(AuthOidcState.state == redirect.state_token)
        .first()
    )
    captured_nonce_box.append(state_row.nonce)
    rtnval = redirect
    return rtnval


# -------------------------------------
# Provider-protocol surface
# -------------------------------------

def test_provider_kind_is_oidc_and_precedence_is_1000():
    """
    **Feature: 1-authentication (M2)**
    **Property: OidcAuthProvider declares OIDC kind and the
    documented PRECEDENCE = 1000 so it wins the tie-break
    against custom in-tenant overrides at PRECEDENCE > 1000
    and loses against PRECEDENCE < 1000 stubs.**
    """
    testbase.assert_equal(
        OidcAuthProvider.provider_kind(), AuthProviderKind.OIDC,
    )
    testbase.assert_equal(OidcAuthProvider.PRECEDENCE, 1000)
    testbase.assert_equal(
        OidcAuthProvider.factory_protocol_name, "auth_provider",
    )
    return


def test_build_begin_login_redirect_returns_authorization_url_and_state():
    """
    **Feature: 1-authentication (M2)**
    **Property: build_begin_login_redirect returns a
    RedirectDescriptor whose target_url is the configured
    authorization_endpoint with state / nonce / pkce
    parameters folded in, and whose state_token matches the
    auth_oidc_state row.**
    """
    session, _config, _box = _setup()
    redirect = OidcAuthProvider.build_begin_login_redirect(
        provider_name="okta", redirect_target="/welcome",
    )
    testbase.assert_equal(isinstance(redirect, RedirectDescriptor), True)
    testbase.assert_equal(
        redirect.target_url.startswith(
            "https://idp.example.com/authorize?",
        ),
        True,
    )
    parsed = urlparse.urlparse(redirect.target_url)
    params = dict(urlparse.parse_qsl(parsed.query))
    testbase.assert_equal(params.get("client_id"), "client-pychestrate")
    testbase.assert_equal(
        params.get("redirect_uri"), "https://app.example.com/cb",
    )
    testbase.assert_equal(params.get("response_type"), "code")
    testbase.assert_equal(params.get("code_challenge_method"), "S256")
    testbase.assert_equal(params.get("state"), redirect.state_token)
    state_rows = session.query(AuthOidcState).all()
    testbase.assert_equal(len(state_rows), 1)
    testbase.assert_equal(state_rows[0].state, redirect.state_token)
    return


# -------------------------------------
# Complete-callback path
# -------------------------------------

def test_complete_callback_seats_session_and_returns_completed_flow():
    """
    **Feature: 1-authentication (M2)**
    **Property: complete_callback runs the OIDC E2E and
    returns a CompletedFlow whose user_id matches the
    seated AuthSession row and whose access/refresh
    payloads round-trip from the IdP.**
    """
    session, _config, captured_nonce_box = _setup()
    redirect = _begin_and_capture_nonce(
        session=session, captured_nonce_box=captured_nonce_box,
    )
    inbound = InboundFlowPayload(
        fields={
            "state": redirect.state_token,
            "code": "auth-code-xyz",
            "request_fingerprint": RequestFingerprint(
                ip_fingerprint="ip-h", user_agent_fingerprint="ua-h",
            ),
            "db_session": session,
        },
    )
    completed = OidcAuthProvider.complete_callback(
        provider_name="okta", inbound=inbound,
    )
    testbase.assert_equal(completed.provider_kind, AuthProviderKind.OIDC)
    testbase.assert_equal(completed.provider_name, "okta")
    testbase.assert_equal(completed.access_token_payload, b"access-bytes")
    testbase.assert_equal(completed.refresh_token_payload, b"refresh-bytes")
    seated = (
        session.query(AuthSession)
        .filter(AuthSession.user_id == completed.user_id)
        .first()
    )
    testbase.assert_equal(seated is not None, True)
    testbase.assert_equal(seated.provider_kind, AuthProviderKind.OIDC)
    return


def test_complete_callback_bubbles_state_unknown_when_state_forged():
    """
    **Feature: 1-authentication (M2)**
    **Property: a forged state value bubbles
    OidcCallbackError unchanged so the controller can
    surface a 400 without leaking detail.**
    """
    session, _config, _box = _setup()
    inbound = InboundFlowPayload(
        fields={
            "state": "forged",
            "code": "c",
            "request_fingerprint": RequestFingerprint(
                ip_fingerprint="ip", user_agent_fingerprint="ua",
            ),
            "db_session": session,
        },
    )
    raised_reason = ""
    try:
        OidcAuthProvider.complete_callback(
            provider_name="okta", inbound=inbound,
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "state_unknown")
    return


def test_complete_callback_validates_inbound_required_fields():
    """
    **Feature: 1-authentication (M2)**
    **Property: missing 'state' / 'code' / 'request_fingerprint'
    raise ValueError so the controller refuses to dispatch a
    half-shaped request.**
    """
    _setup()
    bad_state = InboundFlowPayload(fields={"code": "c"})
    bad_code = InboundFlowPayload(fields={"state": "s"})
    bad_fp = InboundFlowPayload(
        fields={"state": "s", "code": "c", "request_fingerprint": "not-a-fp"},
    )
    raised_a = False
    raised_b = False
    raised_c = False
    try:
        OidcAuthProvider.complete_callback(
            provider_name="okta", inbound=bad_state,
        )
    except ValueError:
        raised_a = True
    try:
        OidcAuthProvider.complete_callback(
            provider_name="okta", inbound=bad_code,
        )
    except ValueError:
        raised_b = True
    try:
        OidcAuthProvider.complete_callback(
            provider_name="okta", inbound=bad_fp,
        )
    except ValueError:
        raised_c = True
    testbase.assert_equal(raised_a, True)
    testbase.assert_equal(raised_b, True)
    testbase.assert_equal(raised_c, True)
    return


def test_complete_callback_unknown_provider_raises_key_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: dispatching against an unregistered
    provider_name surfaces KeyError so the controller
    returns a 404 (the URL segment doesn't map to a
    configured IdP).**
    """
    reset_provider_registry()
    inbound = InboundFlowPayload(
        fields={
            "state": "s", "code": "c",
            "request_fingerprint": RequestFingerprint(
                ip_fingerprint="i", user_agent_fingerprint="u",
            ),
        },
    )
    raised = False
    try:
        OidcAuthProvider.complete_callback(
            provider_name="missing", inbound=inbound,
        )
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Provider registry
# -------------------------------------

def test_provider_registry_register_get_list_round_trip():
    """
    **Feature: 1-authentication (M2)**
    **Property: register / get / list round-trip the same
    OidcProviderConfig instance and list returns sorted
    names.**
    """
    session, config, _box = _setup(provider_name="okta")
    second = _build_config(session=session, provider_name="auth0")
    register_oidc_provider(config=second)
    testbase.assert_equal(
        list_oidc_provider_names(), ["auth0", "okta"],
    )
    testbase.assert_equal(
        get_oidc_provider_config(provider_name="okta") is config, True,
    )
    return


def test_provider_registry_rejects_duplicate_registration():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second register_oidc_provider with the
    same provider_name raises ValueError so a config typo
    can't silently override a real provider at startup.**
    """
    session, config, _box = _setup(provider_name="okta")
    duplicate = _build_config(session=session, provider_name="okta")
    raised = False
    try:
        register_oidc_provider(config=duplicate)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_provider_registry_rejects_empty_required_fields():
    """
    **Feature: 1-authentication (M2)**
    **Property: any empty required field on the
    OidcProviderConfig raises ValueError so misconfigured
    providers fail loudly at startup.**
    """
    reset_provider_registry()
    _engine, session = build_in_memory_session()
    base = _build_config(session=session)
    bad_token_endpoint = OidcProviderConfig(
        provider_name=base.provider_name,
        authorization_endpoint=base.authorization_endpoint,
        token_endpoint="",
        expected_issuer=base.expected_issuer,
        client_id=base.client_id,
        redirect_uri=base.redirect_uri,
        token_fetcher=base.token_fetcher,
        key_resolver=base.key_resolver,
        session_factory=base.session_factory,
    )
    raised = False
    try:
        register_oidc_provider(config=bad_token_endpoint)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_provider_registry_get_unknown_raises_key_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: get_oidc_provider_config raises KeyError on
    an unregistered name; reset_for_testing clears the
    registry between tests.**
    """
    reset_provider_registry()
    raised = False
    try:
        get_oidc_provider_config(provider_name="never-registered")
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(list_oidc_provider_names(), [])
    return
