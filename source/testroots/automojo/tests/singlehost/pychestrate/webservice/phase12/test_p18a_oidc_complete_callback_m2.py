"""
.. module:: test_p18a_oidc_complete_callback_m2
    :synopsis: Tests for P18a — 1-authentication M2 OIDC complete_callback.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.models import AuthOidcState
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    CompleteCallbackResult,
    OidcCallbackError,
    begin_oidc_login,
    complete_oidc_callback,
)
from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    JwksKey,
    encode_test_token,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeError,
    TokenExchangeRawResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
    exchange_code_for_tokens,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


HS256_KEY: bytes = b"\xab" * 32


def _build_token(
        *,
        nonce: str = "fixed-nonce",
        anchor: Optional[datetime] = None,
        issuer: str = "https://idp.example.com",
        audience: str = "client-pychestrate"
    ) -> str:
    materialized_anchor = (
        anchor if anchor is not None else
        datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    )
    header = {"alg": "HS256", "typ": "JWT", "kid": "kid-1"}
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": "user-abc",
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
        if kid == "kid-1":
            return JwksKey(kid="kid-1", alg="HS256", key=HS256_KEY)
        return None
    return _inner


def _begin_flow(*, session, anchor: Optional[datetime] = None):
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
        status_code: int = 200,
        extra: Optional[Mapping[str, Any]] = None
    ):
    def _fetcher(request: TokenExchangeRequest) -> TokenExchangeRawResponse:
        payload = {
            "id_token": id_token,
            "access_token": "access-token-bytes",
            "refresh_token": "refresh-token-bytes",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        if extra is not None:
            payload.update(extra)
        return TokenExchangeRawResponse(
            status_code=status_code, payload=payload,
        )
    return _fetcher


# -------------------------------------
# token_exchange primitives
# -------------------------------------

def test_exchange_code_for_tokens_returns_typed_response():
    """
    **Feature: 1-authentication (M2)**
    **Property: a 200 response with id_token + access_token
    decodes into a TokenExchangeResponse with the
    canonical fields populated.**
    """
    fetcher = _make_fetcher(id_token="encoded-id-token")
    request = TokenExchangeRequest(
        token_endpoint="https://idp.example.com/token",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        code="auth-code-123",
        pkce_verifier="verifier-bytes",
    )
    response = exchange_code_for_tokens(
        request=request, fetcher=fetcher,
    )
    testbase.assert_equal(response.id_token, "encoded-id-token")
    testbase.assert_equal(response.access_token, "access-token-bytes")
    testbase.assert_equal(response.refresh_token, "refresh-token-bytes")
    testbase.assert_equal(response.expires_in_seconds, 3600)
    return


def test_exchange_code_for_tokens_rejects_http_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: a non-2xx HTTP status raises with
    reason='http_error'.**
    """
    def _fetcher(request):
        return TokenExchangeRawResponse(
            status_code=502, payload={"error": "bad_gateway"},
        )

    request = TokenExchangeRequest(
        token_endpoint="https://idp.example.com/token",
        client_id="client", redirect_uri="https://app/cb",
        code="c", pkce_verifier="v",
    )
    raised_reason = ""
    try:
        exchange_code_for_tokens(request=request, fetcher=_fetcher)
    except TokenExchangeError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "http_error")
    return


def test_exchange_code_for_tokens_rejects_provider_error():
    """
    **Feature: 1-authentication (M2)**
    **Property: a 200 response carrying an ``error`` field
    (per RFC 6749) raises with reason='provider_rejected'.**
    """
    def _fetcher(request):
        return TokenExchangeRawResponse(
            status_code=200,
            payload={
                "error": "invalid_grant",
                "error_description": "code expired",
            },
        )

    request = TokenExchangeRequest(
        token_endpoint="https://idp.example.com/token",
        client_id="client", redirect_uri="https://app/cb",
        code="c", pkce_verifier="v",
    )
    raised_reason = ""
    try:
        exchange_code_for_tokens(request=request, fetcher=_fetcher)
    except TokenExchangeError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "provider_rejected")
    return


def test_exchange_code_for_tokens_rejects_missing_id_token():
    """
    **Feature: 1-authentication (M2)**
    **Property: a 200 response without an ``id_token``
    field raises with reason='payload_invalid'.**
    """
    def _fetcher(request):
        return TokenExchangeRawResponse(
            status_code=200,
            payload={"access_token": "only-this"},
        )

    request = TokenExchangeRequest(
        token_endpoint="https://idp.example.com/token",
        client_id="client", redirect_uri="https://app/cb",
        code="c", pkce_verifier="v",
    )
    raised_reason = ""
    try:
        exchange_code_for_tokens(request=request, fetcher=_fetcher)
    except TokenExchangeError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "payload_invalid")
    return


def test_exchange_code_for_tokens_rejects_none_response():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fetcher returning None raises
    payload_invalid so callers detect a misbehaving stub.**
    """
    request = TokenExchangeRequest(
        token_endpoint="https://idp.example.com/token",
        client_id="client", redirect_uri="https://app/cb",
        code="c", pkce_verifier="v",
    )
    raised_reason = ""
    try:
        exchange_code_for_tokens(request=request, fetcher=lambda r: None)
    except TokenExchangeError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "payload_invalid")
    return


# -------------------------------------
# complete_oidc_callback happy path
# -------------------------------------

def test_complete_oidc_callback_happy_path():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fresh begin → callback round trip
    consumes the state row, exchanges the code, validates
    the id_token, and returns CompleteCallbackResult.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin_flow(session=session, anchor=anchor)
    id_token = _build_token(nonce=redirect.nonce, anchor=anchor)
    fetcher = _make_fetcher(id_token=id_token)
    result = complete_oidc_callback(
        db_session=session,
        state=redirect.state,
        code="ic_code",
        provider_name="okta",
        token_endpoint="https://idp.example.com/token",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        token_fetcher=fetcher,
        key_resolver=_resolver(),
        expected_issuer="https://idp.example.com",
        now=anchor,
    )
    testbase.assert_equal(
        result.id_token.payload.get("sub"), "user-abc",
    )
    testbase.assert_equal(
        result.token_response.access_token, "access-token-bytes",
    )
    testbase.assert_equal(result.redirect_target, "/welcome")
    # State row was deleted on consume.
    survivors = session.query(AuthOidcState).all()
    testbase.assert_equal(len(survivors), 0)
    return


# -------------------------------------
# complete_oidc_callback failure modes
# -------------------------------------

def test_complete_oidc_callback_unknown_state():
    """
    **Feature: 1-authentication (M2)**
    **Property: a state value the server never issued
    raises OidcCallbackError(reason='state_unknown').**
    """
    _engine, session = build_in_memory_session()
    raised_reason = ""
    try:
        complete_oidc_callback(
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
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "state_unknown")
    return


def test_complete_oidc_callback_provider_mismatch():
    """
    **Feature: 1-authentication (M2)**
    **Property: a state row issued for one provider cannot
    be replayed against another provider's callback —
    surfaces as 'provider_mismatch'.**
    """
    _engine, session = build_in_memory_session()
    redirect = _begin_flow(session=session)
    id_token = _build_token(nonce=redirect.nonce)
    fetcher = _make_fetcher(id_token=id_token)
    raised_reason = ""
    try:
        complete_oidc_callback(
            db_session=session,
            state=redirect.state,
            code="c",
            provider_name="auth0",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=fetcher,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "provider_mismatch")
    return


def test_complete_oidc_callback_token_exchange_failed():
    """
    **Feature: 1-authentication (M2)**
    **Property: a token-exchange failure surfaces as
    OidcCallbackError(reason='token_exchange_failed') with
    the cause carrying the underlying TokenExchangeError
    reason.**
    """
    _engine, session = build_in_memory_session()
    redirect = _begin_flow(session=session)

    def _bad_fetcher(request):
        return TokenExchangeRawResponse(
            status_code=400, payload={"error": "invalid_grant"},
        )

    raised_reason = ""
    raised_cause = None
    try:
        complete_oidc_callback(
            db_session=session,
            state=redirect.state,
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=_bad_fetcher,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
        raised_cause = err.cause
    testbase.assert_equal(raised_reason, "token_exchange_failed")
    testbase.assert_equal(raised_cause, "http_error")
    return


def test_complete_oidc_callback_id_token_invalid():
    """
    **Feature: 1-authentication (M2)**
    **Property: an id_token that fails validation surfaces
    as OidcCallbackError(reason='id_token_invalid') with
    the underlying validator reason in cause.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin_flow(session=session, anchor=anchor)
    # Forge a token whose nonce mismatches the state-row
    # nonce.
    bad_id_token = _build_token(nonce="forged-nonce", anchor=anchor)
    fetcher = _make_fetcher(id_token=bad_id_token)
    raised_reason = ""
    raised_cause = None
    try:
        complete_oidc_callback(
            db_session=session,
            state=redirect.state,
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=fetcher,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
            now=anchor,
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
        raised_cause = err.cause
    testbase.assert_equal(raised_reason, "id_token_invalid")
    testbase.assert_equal(raised_cause, "nonce_mismatch")
    return


def test_complete_oidc_callback_replay_consumes_state_only_once():
    """
    **Feature: 1-authentication (M2)**
    **Property: a successful callback consumes the state
    row; a replay against the same state surfaces
    state_unknown.**
    """
    _engine, session = build_in_memory_session()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    redirect = _begin_flow(session=session, anchor=anchor)
    id_token = _build_token(nonce=redirect.nonce, anchor=anchor)
    fetcher = _make_fetcher(id_token=id_token)
    complete_oidc_callback(
        db_session=session,
        state=redirect.state,
        code="c",
        provider_name="okta",
        token_endpoint="https://idp.example.com/token",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        token_fetcher=fetcher,
        key_resolver=_resolver(),
        expected_issuer="https://idp.example.com",
        now=anchor,
    )
    raised_reason = ""
    try:
        complete_oidc_callback(
            db_session=session,
            state=redirect.state,
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=fetcher,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
            now=anchor,
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "state_unknown")
    return


def test_complete_oidc_callback_rejects_empty_state():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty state value short-circuits with
    state_unknown.**
    """
    _engine, session = build_in_memory_session()
    raised_reason = ""
    try:
        complete_oidc_callback(
            db_session=session,
            state="",
            code="c",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=lambda r: None,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "state_unknown")
    return


def test_complete_oidc_callback_rejects_empty_code():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty code value short-circuits with
    id_token_invalid (the IdP path can't produce a token
    without a code).**
    """
    _engine, session = build_in_memory_session()
    raised_reason = ""
    try:
        complete_oidc_callback(
            db_session=session,
            state="some-state",
            code="",
            provider_name="okta",
            token_endpoint="https://idp.example.com/token",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=lambda r: None,
            key_resolver=_resolver(),
            expected_issuer="https://idp.example.com",
        )
    except OidcCallbackError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "id_token_invalid")
    return
