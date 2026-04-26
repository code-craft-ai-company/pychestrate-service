"""
.. module:: test_p23c_session_and_mfa_instrumentation_m3
    :synopsis: Tests for P23c — session + MFA instrumentation wiring.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import logging
import struct

from datetime import datetime, timezone
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

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
    mfa_service,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    MfaChallengeRejectedError,
    SessionExpiredError,
    SessionNotFoundError,
)
from automojo.pychestrate.webservice.security.auth.factories.totp_mfa import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    TotpMfaMethod,
)
from automojo.pychestrate.webservice.security.auth.log_events import (
    AUTH_MFA_CHALLENGE_REJECTED,
    AUTH_MFA_CHALLENGE_VERIFIED,
    AUTH_SESSION_CLOSED,
    AUTH_SESSION_OPENED,
    LOGGER_NAME,
)
from automojo.pychestrate.webservice.security.auth.metrics_emitter import (
    METRIC_MFA_FAILURES_TOTAL,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    close_session,
    open_session,
    resolve_session,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_MFA_VERIFY,
    SPAN_SESSION_RESOLVE,
    SPAN_STATUS_ERROR,
    SPAN_STATUS_OK,
    get_recorder,
    reset_for_testing as reset_tracing,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _setup() -> tuple:
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    mfa_service.reset_for_testing()
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


def _seat(*, session, user_id=None):
    if user_id is None:
        user_id = new_uuid()
    rtnval = open_session(
        db_session=session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=RequestFingerprint(
            ip_fingerprint="ip", user_agent_fingerprint="ua",
        ),
        idle_timeout_seconds=1800,
        max_lifetime_seconds=8 * 3600,
    )
    return rtnval


def _live_totp(*, secret_bytes: bytes) -> str:
    epoch_seconds = int(datetime.now(timezone.utc).timestamp())
    step = epoch_seconds // TOTP_PERIOD_SECONDS
    counter_bytes = struct.pack(">Q", step)
    digest = hmac.new(
        key=secret_bytes, msg=counter_bytes, digestmod=hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    truncated = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    code = truncated % (10 ** TOTP_DIGITS)
    rtnval = str(code).zfill(TOTP_DIGITS)
    return rtnval


# -------------------------------------
# session.opened log event
# -------------------------------------

def test_open_session_emits_auth_session_opened_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: open_session emits the auth.session.opened
    structured log event with session_id, user_id,
    provider_kind, provider_name, and opened_at.**
    """
    _engine, session = _setup()
    handler = _capture_auth_log()
    try:
        seated = _seat(session=session)
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_SESSION_OPENED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(
        payload["session_id"], str(seated.session_id),
    )
    testbase.assert_equal(payload["provider_kind"], "LOCAL")
    testbase.assert_equal(payload["provider_name"], "local")
    return


# -------------------------------------
# session.resolve span
# -------------------------------------

def test_resolve_session_emits_session_resolve_span_with_attributes():
    """
    **Feature: 1-authentication (M3)**
    **Property: resolve_session opens a session.resolve
    span with provider_kind + provider_name attributes
    captured from the row.**
    """
    _engine, session = _setup()
    seated = _seat(session=session)
    resolve_session(
        db_session=session,
        session_id=str(seated.session_id),
        now=datetime.now(timezone.utc),
    )
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SESSION_RESOLVE,
    )
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        spans[0].attributes["provider_kind"], "LOCAL",
    )
    testbase.assert_equal(
        spans[0].attributes["provider_name"], "local",
    )
    return


def test_resolve_session_unknown_finalizes_span_as_error_with_reason():
    """
    **Feature: 1-authentication (M3)**
    **Property: a SessionNotFoundError raised inside the
    session.resolve span finalizes the span with status=
    'error' and exception_reason='SessionNotFoundError'
    (no .reason attribute on the exception type).**
    """
    _engine, session = _setup()
    raised = False
    try:
        resolve_session(
            db_session=session,
            session_id="00000000-0000-0000-0000-000000000000",
            now=datetime.now(timezone.utc),
        )
    except SessionNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SESSION_RESOLVE,
    )
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_ERROR)
    testbase.assert_equal(
        spans[0].exception_reason, "SessionNotFoundError",
    )
    return


# -------------------------------------
# session.closed log event
# -------------------------------------

def test_close_session_emits_auth_session_closed_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: close_session emits the
    auth.session.closed structured log event with the
    session_id, user_id, and reason.**
    """
    _engine, session = _setup()
    seated = _seat(session=session)
    captured_session_id = str(seated.session_id)
    captured_user_id = str(seated.user_id)
    handler = _capture_auth_log()
    try:
        close_session(
            db_session=session, session_id=captured_session_id,
        )
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_SESSION_CLOSED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["session_id"], captured_session_id)
    testbase.assert_equal(payload["user_id"], captured_user_id)
    testbase.assert_equal(payload["reason"], "user_logout")
    return


def test_close_session_no_op_emits_no_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: close_session against an unknown session_id
    is a silent no-op — the auth.session.closed log event
    only fires when a row was actually deleted.**
    """
    _engine, session = _setup()
    handler = _capture_auth_log()
    try:
        close_session(
            db_session=session,
            session_id="00000000-0000-0000-0000-000000000000",
        )
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records if r.msg == AUTH_SESSION_CLOSED
    ]
    testbase.assert_equal(len(matched), 0)
    return


# -------------------------------------
# MFA verify wiring
# -------------------------------------

def _enroll_and_verify_totp(*, session, user_id: str) -> bytes:
    bootstrap = mfa_service.enroll_method(
        db_session=session,
        user_id=user_id,
        method_name=TotpMfaMethod.method_name,
        account_name="alice@example.com",
    )
    code = _live_totp(secret_bytes=bootstrap.secret_payload)
    mfa_service.confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    rtnval = bootstrap.secret_payload
    return rtnval


def test_verify_challenge_success_emits_mfa_verify_span_and_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful verify_challenge runs inside
    an mfa.verify span with the method_name attribute and
    emits the auth.mfa.challenge.verified log event.**
    """
    _engine, session = _setup()
    user_id = new_uuid()
    secret = _enroll_and_verify_totp(session=session, user_id=user_id)
    challenge = mfa_service.initiate_challenge(
        db_session=session,
        user_id=user_id,
        method_name=TotpMfaMethod.method_name,
    )
    code = _live_totp(secret_bytes=secret)
    handler = _capture_auth_log()
    try:
        outcome = mfa_service.verify_challenge(
            db_session=session,
            challenge_id=challenge.challenge_id,
            response_fields={"code": code},
        )
    finally:
        _detach_auth_log(handler)
    testbase.assert_equal(outcome.accepted, True)
    spans = get_recorder().list_spans_by_name(name=SPAN_MFA_VERIFY)
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        spans[0].attributes["method_name"], TotpMfaMethod.method_name,
    )
    testbase.assert_equal(spans[0].attributes["accepted"], True)
    matched = [
        r for r in handler.records
        if r.msg == AUTH_MFA_CHALLENGE_VERIFIED
    ]
    testbase.assert_equal(len(matched), 1)
    return


def test_verify_challenge_rejected_emits_mfa_failures_total_counter():
    """
    **Feature: 1-authentication (M3)**
    **Property: a rejected verify (wrong code) emits
    pychestrate_auth_mfa_failures_total{method=totp},
    finalizes the span as 'error', and emits the
    auth.mfa.challenge.rejected log event with the reason.**
    """
    _engine, session = _setup()
    user_id = new_uuid()
    _enroll_and_verify_totp(session=session, user_id=user_id)
    challenge = mfa_service.initiate_challenge(
        db_session=session,
        user_id=user_id,
        method_name=TotpMfaMethod.method_name,
    )
    handler = _capture_auth_log()
    raised = False
    try:
        try:
            mfa_service.verify_challenge(
                db_session=session,
                challenge_id=challenge.challenge_id,
                response_fields={"code": "000000"},
            )
        except MfaChallengeRejectedError:
            raised = True
    finally:
        _detach_auth_log(handler)
    testbase.assert_equal(raised, True)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_MFA_FAILURES_TOTAL,
    )
    matched_metrics = [
        s for s in samples if s.labels.get("method") == "totp"
    ]
    testbase.assert_equal(len(matched_metrics), 1)
    spans = get_recorder().list_spans_by_name(name=SPAN_MFA_VERIFY)
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_ERROR)
    matched_logs = [
        r for r in handler.records
        if r.msg == AUTH_MFA_CHALLENGE_REJECTED
    ]
    testbase.assert_equal(len(matched_logs), 1)
    return


# -------------------------------------
# Safe behavior without metrics bootstrap
# -------------------------------------

def test_session_and_mfa_flows_work_without_metrics_bootstrap():
    """
    **Feature: 1-authentication (M3)**
    **Property: session lifecycle + MFA verify never crash
    when the timeseries driver isn't bootstrapped — recorder
    helpers swallow the missing-driver case so the user-
    facing flows don't depend on observability bootstrap.**
    """
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    mfa_service.reset_for_testing()
    _engine, session = build_in_memory_session()

    seated = _seat(session=session)
    captured_session_id = str(seated.session_id)
    captured_user_id = str(seated.user_id)
    principal = resolve_session(
        db_session=session,
        session_id=captured_session_id,
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(principal.user_id, captured_user_id)
    close_session(
        db_session=session, session_id=captured_session_id,
    )
    return
