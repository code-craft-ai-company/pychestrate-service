"""
.. module:: test_p17a_oidc_begin_login_m2
    :synopsis: Tests for P17a — 1-authentication M2 OIDC begin-login.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from urllib import parse as urlparse

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.models import AuthOidcState
from automojo.pychestrate.webservice.security.auth.oidc import (
    flow as oidc_flow,
    pkce as oidc_pkce,
    state as oidc_state,
)
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    BeginLoginRedirect,
    begin_oidc_login,
)
from automojo.pychestrate.webservice.security.auth.oidc.pkce import (
    PKCE_CHALLENGE_METHOD,
    compute_challenge,
    generate_pkce_pair,
    verify_challenge,
)
from automojo.pychestrate.webservice.security.auth.oidc.state import (
    DEFAULT_STATE_TTL,
    consume_state,
    insert_state,
    sweep_expired,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


# -------------------------------------
# PKCE primitives
# -------------------------------------

def test_pkce_pair_method_is_s256():
    """
    **Feature: 1-authentication (M2)**
    **Property: generate_pkce_pair always declares the S256
    method.**
    """
    pair = generate_pkce_pair()
    testbase.assert_equal(pair.method, PKCE_CHALLENGE_METHOD)
    testbase.assert_equal(pair.method, "S256")
    return


def test_pkce_pair_verifier_is_url_safe_and_long_enough():
    """
    **Feature: 1-authentication (M2)**
    **Property: the verifier is base64url with no padding
    and at least 43 chars (RFC 7636 lower bound).**
    """
    pair = generate_pkce_pair()
    testbase.assert_equal(len(pair.verifier) >= 43, True)
    testbase.assert_equal(len(pair.verifier) <= 128, True)
    testbase.assert_equal("=" not in pair.verifier, True)
    for ch in pair.verifier:
        ok = ch.isalnum() or ch in ("-", "_")
        testbase.assert_equal(ok, True)
    return


def test_pkce_pair_is_unique_across_calls():
    """
    **Feature: 1-authentication (M2)**
    **Property: each generate_pkce_pair call produces a
    fresh verifier + challenge pair.**
    """
    a = generate_pkce_pair()
    b = generate_pkce_pair()
    testbase.assert_equal(a.verifier == b.verifier, False)
    testbase.assert_equal(a.challenge == b.challenge, False)
    return


def test_pkce_compute_challenge_matches_pair_challenge():
    """
    **Feature: 1-authentication (M2)**
    **Property: compute_challenge re-derives the challenge
    from the verifier so the M3 callback path can re-verify
    a pair.**
    """
    pair = generate_pkce_pair()
    testbase.assert_equal(
        compute_challenge(verifier=pair.verifier), pair.challenge,
    )
    testbase.assert_equal(
        verify_challenge(verifier=pair.verifier, challenge=pair.challenge),
        True,
    )
    return


def test_pkce_verify_rejects_mismatched_challenge():
    """
    **Feature: 1-authentication (M2)**
    **Property: verify_challenge rejects a forged
    challenge.**
    """
    pair = generate_pkce_pair()
    testbase.assert_equal(
        verify_challenge(verifier=pair.verifier, challenge="forged"),
        False,
    )
    return


def test_pkce_low_entropy_rejected():
    """
    **Feature: 1-authentication (M2)**
    **Property: a verifier_bytes value below 32 raises
    ValueError so callers can't weaken the entropy below
    the RFC bound.**
    """
    raised = False
    try:
        generate_pkce_pair(verifier_bytes=16)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# auth_oidc_state insert + consume + sweep
# -------------------------------------

def test_insert_state_persists_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: insert_state writes a row with the supplied
    state / nonce / pkce_verifier_enc / provider_name.**
    """
    _engine, session = build_in_memory_session()
    insert_state(
        db_session=session,
        state="state-1",
        nonce="nonce-1",
        pkce_verifier=b"verifier-bytes",
        provider_name="okta",
    )
    row = (
        session.query(AuthOidcState)
        .filter(AuthOidcState.state == "state-1")
        .first()
    )
    testbase.assert_equal(row is not None, True)
    testbase.assert_equal(row.nonce, "nonce-1")
    testbase.assert_equal(bytes(row.pkce_verifier_enc), b"verifier-bytes")
    return


def test_insert_state_rejects_empty_fields():
    """
    **Feature: 1-authentication (M2)**
    **Property: insert_state raises ValueError on empty
    state / nonce / pkce_verifier / provider_name.**
    """
    _engine, session = build_in_memory_session()
    raised_count = 0
    for kwargs in (
        {"state": ""},
        {"nonce": ""},
        {"pkce_verifier": b""},
        {"provider_name": ""},
    ):
        bound = {
            "state": "s", "nonce": "n",
            "pkce_verifier": b"v", "provider_name": "p",
        }
        bound.update(kwargs)
        try:
            insert_state(db_session=session, **bound)
        except ValueError:
            raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 4)
    return


def test_consume_state_returns_record_and_deletes_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: consume_state returns a StateRecord and
    removes the row so a replay returns None.**
    """
    _engine, session = build_in_memory_session()
    insert_state(
        db_session=session,
        state="state-2",
        nonce="nonce-2",
        pkce_verifier=b"verifier-2",
        provider_name="auth0",
        redirect_target="/dashboard",
    )
    captured = consume_state(db_session=session, state="state-2")
    testbase.assert_equal(captured is not None, True)
    testbase.assert_equal(captured.nonce, "nonce-2")
    testbase.assert_equal(captured.redirect_target, "/dashboard")
    testbase.assert_equal(captured.pkce_verifier, b"verifier-2")
    replay = consume_state(db_session=session, state="state-2")
    testbase.assert_equal(replay, None)
    return


def test_consume_state_rejects_unknown_state():
    """
    **Feature: 1-authentication (M2)**
    **Property: consume_state returns None for an unknown
    state — the M3 controller surfaces a 401 without leaking
    which case applied.**
    """
    _engine, session = build_in_memory_session()
    rtnval = consume_state(db_session=session, state="never-issued")
    testbase.assert_equal(rtnval, None)
    return


def test_consume_state_returns_none_when_expired():
    """
    **Feature: 1-authentication (M2)**
    **Property: consume_state returns None when the row's
    expires_at has passed, even though the row itself is
    deleted on the way out.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    insert_state(
        db_session=session,
        state="state-expired",
        nonce="nonce-x",
        pkce_verifier=b"v",
        provider_name="okta",
        ttl=timedelta(seconds=10),
        now=anchor,
    )
    rtnval = consume_state(
        db_session=session,
        state="state-expired",
        now=anchor + timedelta(hours=1),
    )
    testbase.assert_equal(rtnval, None)
    # The row was still deleted on the way out.
    row = (
        session.query(AuthOidcState)
        .filter(AuthOidcState.state == "state-expired")
        .first()
    )
    testbase.assert_equal(row, None)
    return


def test_sweep_expired_drops_past_deadline_rows_only():
    """
    **Feature: 1-authentication (M2)**
    **Property: sweep_expired drops rows past their
    expires_at and leaves rows still inside their TTL
    untouched.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    insert_state(
        db_session=session,
        state="fresh",
        nonce="n",
        pkce_verifier=b"v",
        provider_name="okta",
        ttl=timedelta(hours=1),
        now=anchor,
    )
    insert_state(
        db_session=session,
        state="elapsed",
        nonce="n",
        pkce_verifier=b"v",
        provider_name="okta",
        ttl=timedelta(seconds=1),
        now=anchor,
    )
    removed = sweep_expired(
        db_session=session, now=anchor + timedelta(minutes=10),
    )
    testbase.assert_equal(removed, 1)
    survivors = sorted(
        r.state for r in session.query(AuthOidcState).all()
    )
    testbase.assert_equal(survivors, ["fresh"])
    return


# -------------------------------------
# begin_oidc_login orchestration
# -------------------------------------

def test_begin_oidc_login_persists_state_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: begin_oidc_login writes an auth_oidc_state
    row carrying the state / nonce / pkce_verifier produced
    by the helper.**
    """
    _engine, session = build_in_memory_session()
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/oauth2/authorize",
        client_id="pychestrate-app",
        redirect_uri="https://app.example.com/auth/callback",
    )
    row = (
        session.query(AuthOidcState)
        .filter(AuthOidcState.state == redirect.state)
        .first()
    )
    testbase.assert_equal(row is not None, True)
    testbase.assert_equal(row.nonce, redirect.nonce)
    testbase.assert_equal(
        bytes(row.pkce_verifier_enc),
        redirect.pkce.verifier.encode("ascii"),
    )
    return


def test_begin_oidc_login_authorization_url_carries_required_params():
    """
    **Feature: 1-authentication (M2)**
    **Property: the authorization URL contains every
    required OAuth2 + PKCE param.**
    """
    _engine, session = build_in_memory_session()
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client-abc",
        redirect_uri="https://app.example.com/cb",
        scopes=("openid", "email"),
    )
    parsed = urlparse.urlparse(redirect.authorization_url)
    params = dict(urlparse.parse_qsl(parsed.query))
    testbase.assert_equal(params.get("response_type"), "code")
    testbase.assert_equal(params.get("client_id"), "client-abc")
    testbase.assert_equal(
        params.get("redirect_uri"), "https://app.example.com/cb",
    )
    testbase.assert_equal(params.get("scope"), "openid email")
    testbase.assert_equal(params.get("state"), redirect.state)
    testbase.assert_equal(params.get("nonce"), redirect.nonce)
    testbase.assert_equal(
        params.get("code_challenge"), redirect.pkce.challenge,
    )
    testbase.assert_equal(params.get("code_challenge_method"), "S256")
    return


def test_begin_oidc_login_preserves_endpoint_query_params():
    """
    **Feature: 1-authentication (M2)**
    **Property: an authorization endpoint that already
    carries query params (some IdPs do) keeps them; the
    flow params append after.**
    """
    _engine, session = build_in_memory_session()
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize?prompt=login",
        client_id="client",
        redirect_uri="https://app/cb",
    )
    parsed = urlparse.urlparse(redirect.authorization_url)
    params = dict(urlparse.parse_qsl(parsed.query))
    testbase.assert_equal(params.get("prompt"), "login")
    testbase.assert_equal(params.get("response_type"), "code")
    return


def test_begin_oidc_login_extra_params_fold_in():
    """
    **Feature: 1-authentication (M2)**
    **Property: caller-supplied extra_params fold into the
    authorization URL but do not overwrite the canonical
    OAuth2 + PKCE params.**
    """
    _engine, session = build_in_memory_session()
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client",
        redirect_uri="https://app/cb",
        extra_params={"acr_values": "high", "client_id": "FORGED"},
    )
    parsed = urlparse.urlparse(redirect.authorization_url)
    params = dict(urlparse.parse_qsl(parsed.query))
    testbase.assert_equal(params.get("acr_values"), "high")
    testbase.assert_equal(params.get("client_id"), "client")
    return


def test_begin_oidc_login_rejects_empty_inputs():
    """
    **Feature: 1-authentication (M2)**
    **Property: begin_oidc_login raises ValueError on empty
    provider / endpoint / client_id / redirect_uri / scopes.**
    """
    _engine, session = build_in_memory_session()
    base_kwargs = {
        "db_session": session,
        "provider_name": "okta",
        "authorization_endpoint": "https://idp.example.com/authorize",
        "client_id": "client",
        "redirect_uri": "https://app/cb",
    }
    raised_count = 0
    for kwargs in (
        {"provider_name": ""},
        {"authorization_endpoint": ""},
        {"client_id": ""},
        {"redirect_uri": ""},
        {"scopes": ()},
    ):
        bound = dict(base_kwargs)
        bound.update(kwargs)
        try:
            begin_oidc_login(**bound)
        except ValueError:
            raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 5)
    return


def test_begin_oidc_login_redirect_target_persists():
    """
    **Feature: 1-authentication (M2)**
    **Property: the optional redirect_target argument is
    persisted on the state row so the M3 callback path can
    redirect the user to the originally-requested page.**
    """
    _engine, session = build_in_memory_session()
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client",
        redirect_uri="https://app/cb",
        redirect_target="/projects/abc",
    )
    row = (
        session.query(AuthOidcState)
        .filter(AuthOidcState.state == redirect.state)
        .first()
    )
    testbase.assert_equal(row.redirect_target, "/projects/abc")
    return
