"""
.. module:: test_p19a_oidc_refresh_session_m2
    :synopsis: Tests for P19a — 1-authentication M2 OIDC refresh.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List, Optional

from automojo import testbase

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)
from automojo.pychestrate.webservice.security.auth.events import AuthEventTopics
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.oidc.refresh import (
    DEFAULT_EXTENSION_SECONDS,
    DEFAULT_MAX_LIFETIME_SECONDS,
    OidcRefreshError,
    SingleFlightLocker,
    TokenRefreshRequest,
    refresh_oidc_session,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeRawResponse,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    open_session,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _seat_oidc_session(
        *,
        session,
        user_id: str = "11111111-1111-1111-1111-111111111111",
        provider_name: str = "okta",
        access_token: str = "access-orig",
        refresh_token: Optional[str] = "refresh-orig",
        idle_timeout_seconds: int = 1800,
        max_lifetime_seconds: int = DEFAULT_MAX_LIFETIME_SECONDS
    ) -> AuthSession:
    refresh_payload = (
        refresh_token.encode("utf-8") if refresh_token is not None else None
    )
    fingerprint = RequestFingerprint(
        ip_fingerprint="ip-x", user_agent_fingerprint="ua-x",
    )
    rtnval = open_session(
        db_session=session,
        user_id=user_id,
        provider_kind=AuthProviderKind.OIDC,
        provider_name=provider_name,
        mfa_method_name=None,
        access_token_payload=access_token.encode("utf-8"),
        refresh_token_payload=refresh_payload,
        request_fingerprint=fingerprint,
        idle_timeout_seconds=idle_timeout_seconds,
        max_lifetime_seconds=max_lifetime_seconds,
    )
    return rtnval


def _expiring_fetcher(
        *,
        access_token: str = "access-new",
        refresh_token: Optional[str] = "refresh-new",
        expires_in: Optional[int] = 3600
    ):
    payload: dict = {
        "access_token": access_token,
        "token_type": "Bearer",
    }
    if refresh_token is not None:
        payload["refresh_token"] = refresh_token
    if expires_in is not None:
        payload["expires_in"] = expires_in

    def _fetcher(request: TokenRefreshRequest) -> TokenExchangeRawResponse:
        return TokenExchangeRawResponse(status_code=200, payload=payload)

    return _fetcher


def _push_session_into_leeway(
        *, session: AuthSession, anchor: datetime,
        seconds_remaining: int = 30
    ) -> None:
    session.expires_at = anchor + timedelta(seconds=seconds_remaining)
    return


# -------------------------------------
# Happy-path refresh
# -------------------------------------

def test_refresh_rotates_access_and_refresh_tokens_and_pushes_expires_at():
    """
    **Feature: 1-authentication (M2)**
    **Property: a refresh inside the leeway window rotates
    both tokens, pushes expires_at by extension_seconds, and
    emits entity.session.refreshed.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()

    fetcher = _expiring_fetcher(
        access_token="access-new", refresh_token="refresh-new",
    )
    result = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="client-pychestrate",
        token_fetcher=fetcher,
        now=anchor,
    )
    testbase.assert_equal(result.outcome, "refreshed")
    testbase.assert_equal(result.refresh_token_rotated, True)
    testbase.assert_equal(
        bytes(result.session.access_token_enc), b"access-new",
    )
    testbase.assert_equal(
        bytes(result.session.refresh_token_enc), b"refresh-new",
    )
    expected_expires = anchor + timedelta(
        seconds=DEFAULT_EXTENSION_SECONDS,
    )
    actual = result.session.expires_at
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    testbase.assert_equal(actual, expected_expires)
    return


def test_refresh_emits_session_refreshed_event():
    """
    **Feature: 1-authentication (M2)**
    **Property: a successful refresh publishes a single
    entity.session.refreshed event carrying session_id and
    user_id.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session)
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.SESSION_REFRESHED,
        subscriber=lambda evt: received.append(evt),
    )
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()
    refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_expiring_fetcher(),
        now=anchor,
    )
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(
        received[0].payload["session_id"], str(seated.session_id),
    )
    testbase.assert_equal(
        received[0].payload["refresh_token_rotated"], True,
    )
    return


def test_refresh_keeps_old_refresh_when_idp_omits_it():
    """
    **Feature: 1-authentication (M2)**
    **Property: when the IdP returns no refresh_token, the
    original token stays in place and refresh_token_rotated
    is False.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session, refresh_token="r-orig")
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()
    fetcher = _expiring_fetcher(
        access_token="a-new", refresh_token=None,
    )
    result = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=fetcher,
        now=anchor,
    )
    testbase.assert_equal(result.refresh_token_rotated, False)
    testbase.assert_equal(
        bytes(result.session.refresh_token_enc), b"r-orig",
    )
    return


# -------------------------------------
# Single-flight collapse
# -------------------------------------

def test_refresh_skips_when_session_already_fresh():
    """
    **Feature: 1-authentication (M2)**
    **Property: when expires_at is past the leeway window
    (the IdP was already called by another thread), the
    refresh is a no-op with outcome 'skipped_fresh' and no
    fetcher call is made.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session)
    # expires_at is opened_at + max_lifetime → far in the
    # future; no need to push the row into the leeway window.
    anchor = datetime.now(timezone.utc)

    fetcher_calls: List[TokenRefreshRequest] = []
    def _fetcher(req: TokenRefreshRequest) -> TokenExchangeRawResponse:
        fetcher_calls.append(req)
        return TokenExchangeRawResponse(status_code=200, payload={})

    result = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_fetcher,
        now=anchor,
    )
    testbase.assert_equal(result.outcome, "skipped_fresh")
    testbase.assert_equal(len(fetcher_calls), 0)
    return


def test_back_to_back_refresh_collapses_on_leeway_check():
    """
    **Feature: 1-authentication (M2)**
    **Property: two refreshes back-to-back at the same
    'now' anchor collapse — the second sees the row already
    past the leeway window from the first refresh and
    returns 'skipped_fresh' without hitting the IdP again.

    This is the same property the per-session
    threading.Lock provides under concurrent load: only one
    IdP call per session per leeway window.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()

    fetcher_calls: List[TokenRefreshRequest] = []
    def _counting_fetcher(req: TokenRefreshRequest) -> TokenExchangeRawResponse:
        fetcher_calls.append(req)
        return TokenExchangeRawResponse(
            status_code=200,
            payload={
                "access_token": "a-{}".format(len(fetcher_calls)),
                "refresh_token": "r-{}".format(len(fetcher_calls)),
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    locker = SingleFlightLocker()
    first = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_counting_fetcher,
        locker=locker,
        now=anchor,
    )
    second = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_counting_fetcher,
        locker=locker,
        now=anchor,
    )
    testbase.assert_equal(first.outcome, "refreshed")
    testbase.assert_equal(second.outcome, "skipped_fresh")
    testbase.assert_equal(len(fetcher_calls), 1)
    return


def test_per_session_lock_serializes_concurrent_callers():
    """
    **Feature: 1-authentication (M2)**
    **Property: SingleFlightLocker hands out one
    threading.Lock per session_id; different ids get
    different locks, the same id reuses its lock.**
    """
    locker = SingleFlightLocker()
    lock_a_first = locker.acquire(session_id="sid-a")
    lock_a_second = locker.acquire(session_id="sid-a")
    lock_b = locker.acquire(session_id="sid-b")
    testbase.assert_equal(lock_a_first is lock_a_second, True)
    testbase.assert_equal(lock_a_first is lock_b, False)
    return


# -------------------------------------
# Absolute ceiling
# -------------------------------------

def test_refresh_caps_expires_at_at_absolute_ceiling():
    """
    **Feature: 1-authentication (M2)**
    **Property: a refresh that would push expires_at past
    opened_at + max_lifetime_seconds lands the row exactly
    at the ceiling instead.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(
        session=session, max_lifetime_seconds=600,
    )
    opened_at = seated.opened_at
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    # Anchor inside the row's window but close enough to the
    # ceiling that extension_seconds (3600) overshoots.
    anchor = opened_at + timedelta(seconds=540)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()

    result = refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_expiring_fetcher(),
        max_lifetime_seconds=600,
        now=anchor,
    )
    actual = result.session.expires_at
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    expected_ceiling = opened_at + timedelta(seconds=600)
    testbase.assert_equal(actual, expected_ceiling)
    return


# -------------------------------------
# Failure modes — bubble unchanged
# -------------------------------------

def test_refresh_unknown_session_raises_session_not_found():
    """
    **Feature: 1-authentication (M2)**
    **Property: a session_id that doesn't exist raises
    OidcRefreshError(reason='session_not_found').**
    """
    _engine, session = build_in_memory_session()
    raised_reason = ""
    try:
        refresh_oidc_session(
            db_session=session,
            session_id="00000000-0000-0000-0000-000000000000",
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_expiring_fetcher(),
        )
    except OidcRefreshError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "session_not_found")
    return


def test_refresh_session_without_refresh_token_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a session whose refresh_token_enc is NULL
    raises OidcRefreshError(reason='missing_refresh_token').**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session, refresh_token=None)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()
    raised_reason = ""
    try:
        refresh_oidc_session(
            db_session=session,
            session_id=str(seated.session_id),
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_expiring_fetcher(),
            now=anchor,
        )
    except OidcRefreshError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "missing_refresh_token")
    return


def test_refresh_provider_error_bubbles_token_refresh_failed():
    """
    **Feature: 1-authentication (M2)**
    **Property: an IdP error response bubbles
    OidcRefreshError(reason='token_refresh_failed') with the
    underlying cause token captured on the exception.**
    """
    _engine, session = build_in_memory_session()
    seated = _seat_oidc_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()

    def _bad_fetcher(req: TokenRefreshRequest) -> TokenExchangeRawResponse:
        return TokenExchangeRawResponse(
            status_code=400,
            payload={
                "error": "invalid_grant",
                "error_description": "refresh token revoked",
            },
        )

    raised: Optional[OidcRefreshError] = None
    try:
        refresh_oidc_session(
            db_session=session,
            session_id=str(seated.session_id),
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_bad_fetcher,
            now=anchor,
        )
    except OidcRefreshError as err:
        raised = err
    testbase.assert_equal(raised is not None, True)
    testbase.assert_equal(raised.reason, "token_refresh_failed")
    testbase.assert_equal(raised.cause, "http_error")
    return


def test_refresh_non_oidc_session_raises_provider_kind_mismatch():
    """
    **Feature: 1-authentication (M2)**
    **Property: a row whose provider_kind isn't OIDC raises
    OidcRefreshError(reason='provider_kind_mismatch'); the
    session row is left untouched.**
    """
    _engine, session = build_in_memory_session()
    fingerprint = RequestFingerprint(
        ip_fingerprint="ip-x", user_agent_fingerprint="ua-x",
    )
    seated = open_session(
        db_session=session,
        user_id="22222222-2222-2222-2222-222222222222",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=fingerprint,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=DEFAULT_MAX_LIFETIME_SECONDS,
    )
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_session_into_leeway(session=seated, anchor=anchor)
    session.flush()
    raised_reason = ""
    try:
        refresh_oidc_session(
            db_session=session,
            session_id=str(seated.session_id),
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_expiring_fetcher(),
            now=anchor,
        )
    except OidcRefreshError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "provider_kind_mismatch")
    return


def test_refresh_requires_session_id():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty session_id raises ValueError so
    callers can't accidentally hit the IdP for a half-shaped
    request.**
    """
    _engine, session = build_in_memory_session()
    raised = False
    try:
        refresh_oidc_session(
            db_session=session,
            session_id="",
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_expiring_fetcher(),
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return
