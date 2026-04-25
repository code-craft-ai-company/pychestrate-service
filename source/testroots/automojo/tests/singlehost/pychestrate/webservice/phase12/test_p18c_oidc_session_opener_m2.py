"""
.. module:: test_p18c_oidc_session_opener_m2
    :synopsis: Tests for P18c — 1-authentication M2 OIDC session opener.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from automojo import testbase

from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.security.auth.models import (
    AuthOidcState,
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    OidcCallbackError,
    begin_oidc_login,
)
from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    JwksKey,
    encode_test_token,
)
from automojo.pychestrate.webservice.security.auth.oidc.provisioning import (
    ClaimsMissingError,
    UserDeactivatedError,
)
from automojo.pychestrate.webservice.security.auth.oidc.session_opener import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_MAX_LIFETIME_SECONDS,
    OidcLoginResult,
    open_oidc_session,
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


HS256_KEY: bytes = b"\xab" * 32


def _build_id_token(
        *,
        nonce: str,
        anchor: Optional[datetime] = None,
        sub: str = "idp-user-1",
        email: str = "alice@example.com",
        name: str = "Alice",
        zoneinfo: str = "America/Los_Angeles"
    ) -> str:
    materialized_anchor = (
        anchor if anchor is not None else
        datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    )
    header = {"alg": "HS256", "typ": "JWT", "kid": "kid-1"}
    payload = {
        "iss": "https://idp.example.com",
        "aud": "client-pychestrate",
        "sub": sub,
        "email": email,
        "name": name,
        "zoneinfo": zoneinfo,
        "exp": int((materialized_anchor + timedelta(minutes=10)).timestamp()),
        "iat": int(materialized_anchor.timestamp()),
        "nonce": nonce,
    }
    rtnval = encode_test_token(
        header=header, payload=payload, hs256_key=HS256_KEY,
    )
    return rtnval


def _resolver():
    def _inner(kid):
        if kid != "kid-1":
            return None
        return JwksKey(kid="kid-1", alg="HS256", key=HS256_KEY)
    return _inner


def _begin(*, session, anchor: Optional[datetime] = None):
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        redirect_target="/welcome",
    )
    return redirect


def _make_fetcher(
        *,
        id_token: str,
        access_token: str = "access-token-bytes",
        refresh_token: str = "refresh-token-bytes"
    ):
    def _fetcher(request):
        return TokenExchangeRawResponse(
            status_code=200,
            payload={
                "id_token": id_token,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
    return _fetcher


def _fingerprint() -> RequestFingerprint:
    return RequestFingerprint(
        ip_fingerprint="ip-hash-test",
        user_agent_fingerprint="ua-hash-test",
    )


def _kwargs(*, session, redirect, id_token, anchor=None):
    return {
        "db_session": session,
        "state": redirect.state,
        "code": "auth-code-xyz",
        "provider_name": "okta",
        "token_endpoint": "https://idp.example.com/token",
        "client_id": "client-pychestrate",
        "redirect_uri": "https://app.example.com/cb",
        "token_fetcher": _make_fetcher(id_token=id_token),
        "key_resolver": _resolver(),
        "expected_issuer": "https://idp.example.com",
        "request_fingerprint": _fingerprint(),
        "now": anchor,
    }


# -------------------------------------
# Happy paths
# -------------------------------------

def test_open_oidc_session_happy_path_provisions_and_seats_session():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fresh OIDC callback for an unknown user
    completes the callback, provisions the user, opens an
    auth_sessions row, and returns OidcLoginResult.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin(session=session, anchor=anchor)
    id_token = _build_id_token(nonce=redirect.nonce, anchor=anchor)
    result = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect,
            id_token=id_token, anchor=anchor,
        ),
    )
    testbase.assert_equal(result.provisioning_outcome, "provisioned")
    testbase.assert_equal(result.redirect_target, "/welcome")
    testbase.assert_equal(
        result.session.provider_kind, AuthProviderKind.OIDC,
    )
    testbase.assert_equal(result.session.provider_name, "okta")
    testbase.assert_equal(
        bytes(result.session.access_token_enc), b"access-token-bytes",
    )
    testbase.assert_equal(
        bytes(result.session.refresh_token_enc), b"refresh-token-bytes",
    )
    persisted = (
        session.query(AuthSession)
        .filter(AuthSession.session_id == result.session.session_id)
        .first()
    )
    testbase.assert_equal(persisted is not None, True)
    return


def test_open_oidc_session_consumes_state_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: a successful login deletes the
    auth_oidc_state row so a replay is rejected.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin(session=session, anchor=anchor)
    id_token = _build_id_token(nonce=redirect.nonce, anchor=anchor)
    open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect,
            id_token=id_token, anchor=anchor,
        ),
    )
    state_rows = session.query(AuthOidcState).all()
    testbase.assert_equal(len(state_rows), 0)
    return


def test_open_oidc_session_repeat_login_matches_existing_user():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second login from the same IdP user
    matches the existing IdentityUser instead of provisioning
    again.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect_a = _begin(session=session, anchor=anchor)
    id_token_a = _build_id_token(
        nonce=redirect_a.nonce, anchor=anchor, sub="idp-user-7",
    )
    first = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect_a,
            id_token=id_token_a, anchor=anchor,
        ),
    )
    redirect_b = _begin(session=session, anchor=anchor)
    id_token_b = _build_id_token(
        nonce=redirect_b.nonce, anchor=anchor, sub="idp-user-7",
    )
    second = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect_b,
            id_token=id_token_b, anchor=anchor,
        ),
    )
    testbase.assert_equal(second.provisioning_outcome, "matched_by_external_id")
    testbase.assert_equal(
        first.session.user_id, second.session.user_id,
    )
    return


def test_open_oidc_session_uses_default_idle_and_max_lifetime():
    """
    **Feature: 1-authentication (M2)**
    **Property: idle_timeout_seconds default is 30 minutes;
    max_lifetime_seconds default is 8 hours.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin(session=session, anchor=anchor)
    id_token = _build_id_token(nonce=redirect.nonce, anchor=anchor)
    result = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect,
            id_token=id_token, anchor=anchor,
        ),
    )
    testbase.assert_equal(
        result.session.idle_timeout_seconds,
        DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    return


# -------------------------------------
# Failure modes — bubble unchanged
# -------------------------------------

def test_open_oidc_session_unknown_state_bubbles_callback_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: a forged state value bubbles
    OidcCallbackError(reason='state_unknown') without
    seating a session.**
    """
    _engine, session = build_in_memory_session()
    raised_reason = ""
    try:
        open_oidc_session(
            db_session=session,
            state="forged-state",
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=lambda r: None,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
            request_fingerprint=_fingerprint(),
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "state_unknown")
    sessions = session.query(AuthSession).all()
    testbase.assert_equal(len(sessions), 0)
    return


def test_open_oidc_session_deactivated_user_refuses_to_seat_session():
    """
    **Feature: 1-authentication (M2)**
    **Property: when the resolved user is deactivated, the
    helper raises UserDeactivatedError; no session is
    seated.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)

    # Seat the user once + deactivate them.
    redirect_first = _begin(session=session, anchor=anchor)
    id_token_first = _build_id_token(
        nonce=redirect_first.nonce, anchor=anchor,
    )
    first = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect_first,
            id_token=id_token_first, anchor=anchor,
        ),
    )
    user_service.deactivate_user(
        db_session=session, user_id=str(first.session.user_id),
        reason="off-boarded",
    )

    # New login attempt for the same IdP user.
    redirect_second = _begin(session=session, anchor=anchor)
    id_token_second = _build_id_token(
        nonce=redirect_second.nonce, anchor=anchor,
    )
    raised = False
    try:
        open_oidc_session(
            **_kwargs(
                session=session, redirect=redirect_second,
                id_token=id_token_second, anchor=anchor,
            ),
        )
    except UserDeactivatedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_open_oidc_session_missing_email_claim_bubbles_claims_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: a token missing the email claim bubbles
    ClaimsMissingError; no session is seated.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin(session=session, anchor=anchor)
    # Build a token whose payload lacks the email claim.
    bad_payload = {
        "iss": "https://idp.example.com",
        "aud": "client-pychestrate",
        "sub": "idp-no-email",
        "name": "Anon",
        "zoneinfo": "UTC",
        "exp": int((anchor + timedelta(minutes=10)).timestamp()),
        "iat": int(anchor.timestamp()),
        "nonce": redirect.nonce,
    }
    bad_id_token = encode_test_token(
        header={"alg": "HS256", "typ": "JWT", "kid": "kid-1"},
        payload=bad_payload,
        hs256_key=HS256_KEY,
    )
    raised = False
    try:
        open_oidc_session(
            **_kwargs(
                session=session, redirect=redirect,
                id_token=bad_id_token, anchor=anchor,
            ),
        )
    except ClaimsMissingError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_open_oidc_session_requires_fingerprint():
    """
    **Feature: 1-authentication (M2)**
    **Property: missing request_fingerprint raises
    ValueError so the controller surfaces a 500 instead of
    a half-seated session.**
    """
    _engine, session = build_in_memory_session()
    raised = False
    try:
        open_oidc_session(
            db_session=session,
            state="s",
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            redirect_uri="https://app/cb",
            token_fetcher=lambda r: None,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
            request_fingerprint=None,
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_open_oidc_session_redirect_target_round_trips():
    """
    **Feature: 1-authentication (M2)**
    **Property: the redirect_target captured at begin time
    surfaces on the OidcLoginResult so the controller can
    redirect the user to their originally-requested page.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin(session=session, anchor=anchor)
    id_token = _build_id_token(nonce=redirect.nonce, anchor=anchor)
    result = open_oidc_session(
        **_kwargs(
            session=session, redirect=redirect,
            id_token=id_token, anchor=anchor,
        ),
    )
    testbase.assert_equal(result.redirect_target, "/welcome")
    return
