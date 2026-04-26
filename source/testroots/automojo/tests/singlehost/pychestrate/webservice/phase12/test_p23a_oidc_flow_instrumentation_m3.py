"""
.. module:: test_p23a_oidc_flow_instrumentation_m3
    :synopsis: Tests for P23a — OIDC flow instrumentation wiring (metrics + spans + logs).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from automojo import testbase

from automojo.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as register_timeseries_extensions,
    service as metrics_service,
)
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    reset_for_testing as reset_metrics_facade,
)
from automojo.pychestrate.webservice.security.auth import (
    log_events,
    metrics_emitter,
)
from automojo.pychestrate.webservice.security.auth.log_events import (
    AUTH_LOGIN_REJECTED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_SESSION_REFRESHED,
    LOGGER_NAME,
)
from automojo.pychestrate.webservice.security.auth.metrics_emitter import (
    METRIC_LOGIN_TOTAL,
    METRIC_TOKEN_REFRESH_TOTAL,
)
from automojo.pychestrate.webservice.security.auth.models import (
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
from automojo.pychestrate.webservice.security.auth.oidc.refresh import (
    OidcRefreshError,
    SingleFlightLocker,
    refresh_oidc_session,
)
from automojo.pychestrate.webservice.security.auth.oidc.session_opener import (
    open_oidc_session,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeRawResponse,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    open_session,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_OIDC_CALLBACK,
    SPAN_OIDC_REFRESH,
    SPAN_OIDC_TOKEN_EXCHANGE,
    SPAN_STATUS_ERROR,
    SPAN_STATUS_OK,
    get_recorder,
    reset_for_testing as reset_tracing,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


HS256_KEY: bytes = b"\xab" * 32
ANCHOR: datetime = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)


def _id_token_for(*, nonce: str, sub: str = "idp-user-1") -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": "kid-1"}
    payload = {
        "iss": "https://idp.example.com",
        "aud": "client-pychestrate",
        "sub": sub,
        "email": "alice@example.com",
        "name": "Alice",
        "zoneinfo": "UTC",
        "exp": int((ANCHOR + timedelta(minutes=10)).timestamp()),
        "iat": int(ANCHOR.timestamp()),
        "nonce": nonce,
    }
    rtnval = encode_test_token(
        header=header, payload=payload, hs256_key=HS256_KEY,
    )
    return rtnval


def _key_resolver():
    def _inner(kid):
        if kid != "kid-1":
            return None
        return JwksKey(kid="kid-1", alg="HS256", key=HS256_KEY)
    return _inner


def _good_token_fetcher(*, id_token: str):
    def _fetcher(_request):
        return TokenExchangeRawResponse(
            status_code=200,
            payload={
                "id_token": id_token,
                "access_token": "atk-bytes",
                "refresh_token": "rtk-bytes",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
    return _fetcher


def _bad_http_fetcher():
    def _fetcher(_request):
        return TokenExchangeRawResponse(
            status_code=500,
            payload={"error": "server_error"},
        )
    return _fetcher


def _seat_login(*, session, anchor: datetime = ANCHOR):
    redirect = begin_oidc_login(
        db_session=session,
        provider_name="okta",
        authorization_endpoint="https://idp.example.com/authorize",
        client_id="client-pychestrate",
        redirect_uri="https://app.example.com/cb",
        redirect_target="/welcome",
    )
    return redirect


def _open_oidc_kwargs(*, session, redirect, fetcher, anchor: datetime = ANCHOR):
    rtnval = {
        "db_session": session,
        "state": redirect.state,
        "code": "auth-code-xyz",
        "provider_name": "okta",
        "token_endpoint": "https://idp.example.com/token",
        "client_id": "client-pychestrate",
        "redirect_uri": "https://app.example.com/cb",
        "token_fetcher": fetcher,
        "key_resolver": _key_resolver(),
        "expected_issuer": "https://idp.example.com",
        "request_fingerprint": RequestFingerprint(
            ip_fingerprint="ip", user_agent_fingerprint="ua",
        ),
        "now": anchor,
    }
    return rtnval


def _setup_with_metrics() -> tuple:
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    register_timeseries_extensions()
    _engine, session = build_in_memory_session()
    metrics_emitter.register_auth_metrics(db_session=session)
    return _engine, session


class _CapturingHandler(logging.Handler):

    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []
        return

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        return


def _capture_auth_log() -> _CapturingHandler:
    handler = _CapturingHandler()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return handler


def _detach_auth_log(handler: _CapturingHandler) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    return


# -------------------------------------
# open_oidc_session — happy path
# -------------------------------------

def test_happy_login_emits_login_total_succeeded_counter():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful open_oidc_session emits
    pychestrate_auth_login_total{outcome=succeeded} with
    provider_kind=OIDC and provider_name on the labels.**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    id_token = _id_token_for(nonce=redirect.nonce)
    open_oidc_session(
        **_open_oidc_kwargs(
            session=session, redirect=redirect,
            fetcher=_good_token_fetcher(id_token=id_token),
        ),
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_LOGIN_TOTAL,
    )
    matched = [
        s for s in samples
        if s.labels.get("outcome") == "succeeded"
        and s.labels.get("provider_kind") == "OIDC"
        and s.labels.get("provider_name") == "okta"
    ]
    testbase.assert_equal(len(matched), 1)
    testbase.assert_equal(matched[0].value, 1.0)
    return


def test_happy_login_emits_auth_login_succeeded_log_event_with_user_id():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful open_oidc_session emits the
    auth.login.succeeded structured log event with the
    user_id and session_id of the seated row.**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    id_token = _id_token_for(nonce=redirect.nonce)
    handler = _capture_auth_log()
    try:
        result = open_oidc_session(
            **_open_oidc_kwargs(
                session=session, redirect=redirect,
                fetcher=_good_token_fetcher(id_token=id_token),
            ),
        )
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_LOGIN_SUCCEEDED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["provider_name"], "okta")
    testbase.assert_equal(payload["provider_kind"], "OIDC")
    testbase.assert_equal(
        payload["session_id"], str(result.session.session_id),
    )
    testbase.assert_equal(
        payload["user_id"], str(result.session.user_id),
    )
    return


def test_happy_login_emits_oidc_callback_and_token_exchange_spans():
    """
    **Feature: 1-authentication (M3)**
    **Property: open_oidc_session opens an oidc.callback
    span containing an oidc.token_exchange child (both
    finalize with status='ok').**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    id_token = _id_token_for(nonce=redirect.nonce)
    open_oidc_session(
        **_open_oidc_kwargs(
            session=session, redirect=redirect,
            fetcher=_good_token_fetcher(id_token=id_token),
        ),
    )
    callback_spans = get_recorder().list_spans_by_name(
        name=SPAN_OIDC_CALLBACK,
    )
    exchange_spans = get_recorder().list_spans_by_name(
        name=SPAN_OIDC_TOKEN_EXCHANGE,
    )
    testbase.assert_equal(len(callback_spans), 1)
    testbase.assert_equal(callback_spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        callback_spans[0].attributes["provider_name"], "okta",
    )
    testbase.assert_equal(len(exchange_spans), 1)
    testbase.assert_equal(exchange_spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        exchange_spans[0].attributes["status_code"], 200,
    )
    return


# -------------------------------------
# open_oidc_session — failure path
# -------------------------------------

def test_token_exchange_failure_emits_login_total_rejected_counter():
    """
    **Feature: 1-authentication (M3)**
    **Property: a token-exchange failure (HTTP 500 from
    the IdP) bubbles OidcCallbackError, but on the way
    out emits pychestrate_auth_login_total{outcome=rejected}.**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    raised = False
    try:
        open_oidc_session(
            **_open_oidc_kwargs(
                session=session, redirect=redirect,
                fetcher=_bad_http_fetcher(),
            ),
        )
    except OidcCallbackError:
        raised = True
    testbase.assert_equal(raised, True)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_LOGIN_TOTAL,
    )
    rejected = [
        s for s in samples if s.labels.get("outcome") == "rejected"
    ]
    testbase.assert_equal(len(rejected), 1)
    return


def test_token_exchange_failure_emits_auth_login_rejected_log_event_with_reason():
    """
    **Feature: 1-authentication (M3)**
    **Property: a failure surfaces auth.login.rejected with
    the underlying stable reason token (token_exchange_failed
    in this case) on the log payload.**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    handler = _capture_auth_log()
    try:
        try:
            open_oidc_session(
                **_open_oidc_kwargs(
                    session=session, redirect=redirect,
                    fetcher=_bad_http_fetcher(),
                ),
            )
        except OidcCallbackError:
            pass
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_LOGIN_REJECTED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["provider_name"], "okta")
    testbase.assert_equal(
        payload["reason"], "token_exchange_failed",
    )
    return


def test_failure_emits_callback_span_with_error_status_and_reason():
    """
    **Feature: 1-authentication (M3)**
    **Property: an OidcCallbackError emitted inside the
    callback span finalizes the span with status='error'
    and surfaces the error's stable reason on the span.**
    """
    _engine, session = _setup_with_metrics()
    redirect = _seat_login(session=session)
    try:
        open_oidc_session(
            **_open_oidc_kwargs(
                session=session, redirect=redirect,
                fetcher=_bad_http_fetcher(),
            ),
        )
    except OidcCallbackError:
        pass
    callback_spans = get_recorder().list_spans_by_name(
        name=SPAN_OIDC_CALLBACK,
    )
    testbase.assert_equal(len(callback_spans), 1)
    testbase.assert_equal(
        callback_spans[0].status, SPAN_STATUS_ERROR,
    )
    testbase.assert_equal(
        callback_spans[0].exception_reason, "token_exchange_failed",
    )
    return


# -------------------------------------
# refresh_oidc_session instrumentation
# -------------------------------------

def _seat_refreshable_session(*, session) -> AuthSession:
    fingerprint = RequestFingerprint(
        ip_fingerprint="ip", user_agent_fingerprint="ua",
    )
    seated = open_session(
        db_session=session,
        user_id="11111111-1111-1111-1111-111111111111",
        provider_kind=AuthProviderKind.OIDC,
        provider_name="okta",
        mfa_method_name=None,
        access_token_payload=b"atk-old",
        refresh_token_payload=b"rtk-old",
        request_fingerprint=fingerprint,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=8 * 3600,
    )
    return seated


def _push_into_leeway(*, seated: AuthSession, anchor: datetime):
    seated.expires_at = anchor + timedelta(seconds=30)
    return


def _refresh_fetcher(*, access: str, refresh: Optional[str]):
    def _fetcher(_req):
        payload = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        if refresh is not None:
            payload["refresh_token"] = refresh
        return TokenExchangeRawResponse(status_code=200, payload=payload)
    return _fetcher


def test_refresh_emits_oidc_refresh_span_and_record_token_refresh_counter():
    """
    **Feature: 1-authentication (M3)**
    **Property: refresh_oidc_session opens an oidc.refresh
    span and emits pychestrate_auth_token_refresh_total
    {outcome=refreshed} on a successful rotation.**
    """
    _engine, session = _setup_with_metrics()
    seated = _seat_refreshable_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_into_leeway(seated=seated, anchor=anchor)
    session.flush()
    refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_refresh_fetcher(access="atk-new", refresh="rtk-new"),
        locker=SingleFlightLocker(),
        now=anchor,
    )
    spans = get_recorder().list_spans_by_name(name=SPAN_OIDC_REFRESH)
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(spans[0].attributes["outcome"], "refreshed")
    testbase.assert_equal(
        spans[0].attributes["refresh_token_rotated"], True,
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_TOKEN_REFRESH_TOTAL,
    )
    refreshed = [
        s for s in samples if s.labels.get("outcome") == "refreshed"
    ]
    testbase.assert_equal(len(refreshed), 1)
    return


def test_refresh_emits_auth_session_refreshed_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful refresh emits the
    auth.session.refreshed structured log event with the
    session_id, user_id, and refresh_token_rotated
    payload fields.**
    """
    _engine, session = _setup_with_metrics()
    seated = _seat_refreshable_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_into_leeway(seated=seated, anchor=anchor)
    session.flush()
    handler = _capture_auth_log()
    try:
        refresh_oidc_session(
            db_session=session,
            session_id=str(seated.session_id),
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_refresh_fetcher(access="atk-new", refresh="rtk-new"),
            locker=SingleFlightLocker(),
            now=anchor,
        )
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_SESSION_REFRESHED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(
        payload["session_id"], str(seated.session_id),
    )
    testbase.assert_equal(payload["refresh_token_rotated"], True)
    return


def test_refresh_failure_emits_token_refresh_failed_counter_and_error_span():
    """
    **Feature: 1-authentication (M3)**
    **Property: an IdP rejection on refresh emits
    pychestrate_auth_token_refresh_total{outcome=failed}
    and finalizes the oidc.refresh span with status='error'
    + reason=token_refresh_failed.**
    """
    _engine, session = _setup_with_metrics()
    seated = _seat_refreshable_session(session=session)
    anchor = datetime.now(timezone.utc) + timedelta(hours=2)
    _push_into_leeway(seated=seated, anchor=anchor)
    session.flush()

    def _bad_refresh_fetcher(_req):
        return TokenExchangeRawResponse(
            status_code=400,
            payload={
                "error": "invalid_grant",
                "error_description": "refresh token revoked",
            },
        )

    raised = False
    try:
        refresh_oidc_session(
            db_session=session,
            session_id=str(seated.session_id),
            token_endpoint="https://idp.example.com/token",
            client_id="c",
            token_fetcher=_bad_refresh_fetcher,
            locker=SingleFlightLocker(),
            now=anchor,
        )
    except OidcRefreshError:
        raised = True
    testbase.assert_equal(raised, True)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_TOKEN_REFRESH_TOTAL,
    )
    failed = [
        s for s in samples if s.labels.get("outcome") == "failed"
    ]
    testbase.assert_equal(len(failed), 1)
    spans = get_recorder().list_spans_by_name(name=SPAN_OIDC_REFRESH)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_ERROR)
    testbase.assert_equal(
        spans[0].exception_reason, "token_refresh_failed",
    )
    return


def test_refresh_skipped_fresh_emits_skipped_fresh_counter():
    """
    **Feature: 1-authentication (M3)**
    **Property: a refresh that the leeway check skips emits
    pychestrate_auth_token_refresh_total{outcome=skipped_fresh}
    so dashboards can chart the collapse rate.**
    """
    _engine, session = _setup_with_metrics()
    seated = _seat_refreshable_session(session=session)
    # expires_at is opened_at + max_lifetime — far in the
    # future, so the leeway check skips the IdP call.
    anchor = datetime.now(timezone.utc)

    refresh_oidc_session(
        db_session=session,
        session_id=str(seated.session_id),
        token_endpoint="https://idp.example.com/token",
        client_id="c",
        token_fetcher=_refresh_fetcher(access="atk", refresh="rtk"),
        locker=SingleFlightLocker(),
        now=anchor,
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_TOKEN_REFRESH_TOTAL,
    )
    skipped = [
        s for s in samples
        if s.labels.get("outcome") == "skipped_fresh"
    ]
    testbase.assert_equal(len(skipped), 1)
    return


# -------------------------------------
# Safe emission when timeseries driver isn't registered
# -------------------------------------

def test_open_oidc_session_works_when_metrics_driver_not_registered():
    """
    **Feature: 1-authentication (M3)**
    **Property: open_oidc_session never crashes when the
    timeseries driver isn't bootstrapped — the recorder
    helpers swallow the missing-driver case so flows
    don't depend on observability bootstrap.**
    """
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    # Note: NOT registering timeseries extensions, NOT
    # calling register_auth_metrics — the metric writes
    # should no-op rather than crash.
    _engine, session = build_in_memory_session()
    redirect = _seat_login(session=session)
    id_token = _id_token_for(nonce=redirect.nonce)
    result = open_oidc_session(
        **_open_oidc_kwargs(
            session=session, redirect=redirect,
            fetcher=_good_token_fetcher(id_token=id_token),
        ),
    )
    testbase.assert_equal(result.provisioning_outcome, "provisioned")
    return
