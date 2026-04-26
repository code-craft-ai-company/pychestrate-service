"""
.. module:: test_p22a_auth_metrics_and_log_events_m3
    :synopsis: Tests for P22a — auth metrics emitter + scrubbed log events.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.metrics.timeseries import service as metrics_service
from automojo.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as register_timeseries_extensions,
)
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    MetricKind,
    reset_for_testing as reset_metrics_facade,
)
from automojo.pychestrate.webservice.security.auth import metrics_emitter
from automojo.pychestrate.webservice.security.auth import log_events
from automojo.pychestrate.webservice.security.auth.log_events import (
    AUTH_LOGIN_SUCCEEDED,
    LOGGER_NAME,
    SECRET_REDACTED_MARKER,
    emit_log_event,
    redact_secrets,
)
from automojo.pychestrate.webservice.security.auth.metrics_emitter import (
    METRIC_LOCAL_LOGIN_FAILURES_TOTAL,
    METRIC_LOGIN_TOTAL,
    METRIC_MFA_FAILURES_TOTAL,
    METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL,
    METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL,
    METRIC_SESSION_ACTIVE,
    METRIC_TOKEN_REFRESH_TOTAL,
    list_auth_metric_definitions,
    record_local_login_failure,
    record_login,
    record_mfa_failure,
    record_oidc_discovery_refresh_failure,
    record_saml_metadata_refresh_failure,
    record_token_refresh,
    register_auth_metrics,
    set_session_active_count,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _setup_metrics():
    reset_phase1_runtime()
    reset_metrics_facade()
    register_timeseries_extensions()
    _engine, session = build_in_memory_session()
    return session


# -------------------------------------
# register_auth_metrics
# -------------------------------------

def test_register_auth_metrics_seeds_every_definition():
    """
    **Feature: 1-authentication (M3)**
    **Property: register_auth_metrics seeds every metric in
    NFR-3 with its declared MetricKind and label set.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    registered = {d.name: d for d in metrics_service.list_definitions()}
    expected_names = {d.name for d in list_auth_metric_definitions()}
    actual_names = set(registered.keys())
    testbase.assert_equal(
        expected_names.issubset(actual_names), True,
    )
    testbase.assert_equal(
        registered[METRIC_LOGIN_TOTAL].kind, MetricKind.COUNTER,
    )
    testbase.assert_equal(
        registered[METRIC_SESSION_ACTIVE].kind, MetricKind.GAUGE,
    )
    return


def test_register_auth_metrics_is_idempotent():
    """
    **Feature: 1-authentication (M3)**
    **Property: a second register_auth_metrics call doesn't
    raise — the registry simply overwrites the definitions
    with the same instances.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    register_auth_metrics(db_session=session)
    return


# -------------------------------------
# Counter recorders
# -------------------------------------

def test_record_login_writes_counter_with_provider_and_outcome_labels():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_login increments the login_total
    counter with the provider_kind / provider_name / outcome
    labels the spec mandates.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_login(
        db_session=session,
        provider_kind=AuthProviderKind.OIDC,
        provider_name="okta",
        outcome=metrics_emitter.LOGIN_OUTCOME_SUCCEEDED,
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_LOGIN_TOTAL,
    )
    testbase.assert_equal(len(samples), 1)
    sample = samples[0]
    testbase.assert_equal(sample.value, 1.0)
    testbase.assert_equal(sample.labels["provider_kind"], "OIDC")
    testbase.assert_equal(sample.labels["provider_name"], "okta")
    testbase.assert_equal(sample.labels["outcome"], "succeeded")
    return


def test_record_local_login_failure_writes_counter_per_reason():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_local_login_failure emits the
    failures counter with the supplied reason label.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_local_login_failure(
        db_session=session, reason="bad_password",
    )
    record_local_login_failure(
        db_session=session, reason="bad_password",
    )
    record_local_login_failure(
        db_session=session, reason="user_not_found",
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session,
        metric_name=METRIC_LOCAL_LOGIN_FAILURES_TOTAL,
    )
    by_reason = {}
    for sample in samples:
        reason = sample.labels.get("reason")
        by_reason[reason] = by_reason.get(reason, 0) + sample.value
    testbase.assert_equal(by_reason["bad_password"], 2.0)
    testbase.assert_equal(by_reason["user_not_found"], 1.0)
    return


def test_record_mfa_failure_labels_by_method():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_mfa_failure emits the MFA failures
    counter labeled by method name.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_mfa_failure(db_session=session, method_name="totp")
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_MFA_FAILURES_TOTAL,
    )
    testbase.assert_equal(len(samples), 1)
    testbase.assert_equal(samples[0].labels["method"], "totp")
    return


def test_record_oidc_discovery_refresh_failure_labels_by_issuer():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_oidc_discovery_refresh_failure emits
    the failures counter labeled by issuer.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_oidc_discovery_refresh_failure(
        db_session=session, issuer="https://idp.example.com",
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session,
        metric_name=METRIC_OIDC_DISCOVERY_REFRESH_FAILURES_TOTAL,
    )
    testbase.assert_equal(len(samples), 1)
    testbase.assert_equal(
        samples[0].labels["issuer"], "https://idp.example.com",
    )
    return


def test_record_saml_metadata_refresh_failure_labels_by_provider():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_saml_metadata_refresh_failure emits
    the failures counter labeled by provider_name.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_saml_metadata_refresh_failure(
        db_session=session, provider_name="okta-saml",
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session,
        metric_name=METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL,
    )
    testbase.assert_equal(len(samples), 1)
    testbase.assert_equal(
        samples[0].labels["provider_name"], "okta-saml",
    )
    return


def test_record_token_refresh_labels_by_outcome():
    """
    **Feature: 1-authentication (M3)**
    **Property: record_token_refresh emits the refresh
    counter labeled by outcome (refreshed / skipped_fresh /
    failed).**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    record_token_refresh(
        db_session=session,
        outcome=metrics_emitter.TOKEN_REFRESH_OUTCOME_REFRESHED,
    )
    record_token_refresh(
        db_session=session,
        outcome=metrics_emitter.TOKEN_REFRESH_OUTCOME_SKIPPED_FRESH,
    )
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_TOKEN_REFRESH_TOTAL,
    )
    outcomes = sorted([s.labels.get("outcome") for s in samples])
    testbase.assert_equal(outcomes, ["refreshed", "skipped_fresh"])
    return


def test_set_session_active_count_writes_gauge():
    """
    **Feature: 1-authentication (M3)**
    **Property: set_session_active_count writes the
    session_active gauge with the supplied integer.**
    """
    session = _setup_metrics()
    register_auth_metrics(db_session=session)
    set_session_active_count(db_session=session, count=42)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_SESSION_ACTIVE,
    )
    testbase.assert_equal(len(samples), 1)
    testbase.assert_equal(samples[0].value, 42.0)
    return


# -------------------------------------
# Log-event redaction
# -------------------------------------

def test_redact_secrets_replaces_canonical_secret_keys_with_marker():
    """
    **Feature: 1-authentication (M3)**
    **Property: redact_secrets swaps every canonical secret
    field name (id_token, access_token, refresh_token,
    password, etc.) with the SECRET_REDACTED_MARKER.**
    """
    payload = {
        "user_id": "u1",
        "id_token": "eyJ...",
        "access_token": "atk",
        "refresh_token": "rtk",
        "password": "p@ssw0rd",
        "mfa_code": "123456",
        "non_secret": "keep-me",
    }
    redacted = redact_secrets(payload=payload)
    testbase.assert_equal(redacted["user_id"], "u1")
    testbase.assert_equal(redacted["non_secret"], "keep-me")
    testbase.assert_equal(redacted["id_token"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(redacted["access_token"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(redacted["refresh_token"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(redacted["password"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(redacted["mfa_code"], SECRET_REDACTED_MARKER)
    return


def test_redact_secrets_recurses_into_nested_mappings_and_lists():
    """
    **Feature: 1-authentication (M3)**
    **Property: redact_secrets walks nested mappings and
    list-of-mappings so a secret tucked inside an
    'attributes' or 'token_response' sub-payload is still
    scrubbed.**
    """
    payload = {
        "outer": "x",
        "token_response": {
            "id_token": "eyJ...",
            "access_token": "atk",
            "expires_in": 3600,
        },
        "audit": [
            {"event": "step-1", "password": "leak-me"},
            {"event": "step-2", "non_secret": "ok"},
        ],
    }
    redacted = redact_secrets(payload=payload)
    testbase.assert_equal(
        redacted["token_response"]["id_token"], SECRET_REDACTED_MARKER,
    )
    testbase.assert_equal(
        redacted["token_response"]["access_token"], SECRET_REDACTED_MARKER,
    )
    testbase.assert_equal(
        redacted["token_response"]["expires_in"], 3600,
    )
    testbase.assert_equal(
        redacted["audit"][0]["password"], SECRET_REDACTED_MARKER,
    )
    testbase.assert_equal(
        redacted["audit"][1]["non_secret"], "ok",
    )
    return


def test_redact_secrets_accepts_extra_secret_keys():
    """
    **Feature: 1-authentication (M3)**
    **Property: callers can pass extra_secret_keys to redact
    flow-specific secret names not in the canonical set.**
    """
    payload = {"custom_token_field": "abc", "ok": "ok"}
    redacted = redact_secrets(
        payload=payload, extra_secret_keys=["custom_token_field"],
    )
    testbase.assert_equal(
        redacted["custom_token_field"], SECRET_REDACTED_MARKER,
    )
    testbase.assert_equal(redacted["ok"], "ok")
    return


def test_redact_secrets_handles_none_payload():
    """
    **Feature: 1-authentication (M3)**
    **Property: redact_secrets returns an empty dict for
    None — never raises.**
    """
    rtnval = redact_secrets(payload=None)
    testbase.assert_equal(rtnval, {})
    return


# -------------------------------------
# emit_log_event
# -------------------------------------

class _CapturingHandler(logging.Handler):
    """
        Test-only handler that buffers every record so the
        test can assert on payload + level.
    """

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
    logger = logging.getLogger(LOGGER_NAME)
    logger.removeHandler(handler)
    return


def test_emit_log_event_scrubs_secret_fields_before_logging():
    """
    **Feature: 1-authentication (M3)**
    **Property: emit_log_event scrubs secret fields before
    handing the payload to the stdlib logger so a token
    can never reach a log destination.**
    """
    handler = _capture_auth_log()
    try:
        returned = emit_log_event(
            event_name=AUTH_LOGIN_SUCCEEDED,
            payload={
                "user_id": "u1",
                "id_token": "eyJ...",
                "access_token": "atk",
            },
        )
    finally:
        _detach_auth_log(handler)
    testbase.assert_equal(len(handler.records) >= 1, True)
    extra = handler.records[0].__dict__.get("payload", {})
    testbase.assert_equal(extra["user_id"], "u1")
    testbase.assert_equal(extra["id_token"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(extra["access_token"], SECRET_REDACTED_MARKER)
    testbase.assert_equal(returned["id_token"], SECRET_REDACTED_MARKER)
    return


def test_emit_log_event_carries_event_name_on_record():
    """
    **Feature: 1-authentication (M3)**
    **Property: the stable event-name token rides on the
    LogRecord both as the message and as
    record.event_name so log shippers can branch on it.**
    """
    handler = _capture_auth_log()
    try:
        emit_log_event(
            event_name=log_events.AUTH_SESSION_OPENED,
            payload={"session_id": "s1", "user_id": "u1"},
        )
    finally:
        _detach_auth_log(handler)
    record = handler.records[0]
    testbase.assert_equal(record.msg, log_events.AUTH_SESSION_OPENED)
    testbase.assert_equal(
        record.__dict__.get("event_name"),
        log_events.AUTH_SESSION_OPENED,
    )
    return


def test_emit_log_event_honors_caller_supplied_level():
    """
    **Feature: 1-authentication (M3)**
    **Property: emit_log_event passes the caller's level
    through to the logger so rejection events can be
    emitted at WARNING.**
    """
    handler = _capture_auth_log()
    try:
        emit_log_event(
            event_name=log_events.AUTH_LOGIN_REJECTED,
            payload={"reason": "bad_password"},
            level=logging.WARNING,
        )
    finally:
        _detach_auth_log(handler)
    record = handler.records[0]
    testbase.assert_equal(record.levelno, logging.WARNING)
    return
