"""
.. module:: test_p22c_auth_background_sweepers_m3
    :synopsis: Tests for P22c — auth background sweep (oidc_state + saml_replay).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timedelta, timezone
from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.background_sweep import (
    LOG_EVENT_AUTH_BACKGROUND_SWEPT,
    SPAN_AUTH_BACKGROUND_SWEEP,
    SweepReport,
    sweep_auth_caches,
)
from automojo.pychestrate.webservice.security.auth.log_events import (
    LOGGER_NAME,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthOidcState,
    AuthSamlReplayCache,
)
from automojo.pychestrate.webservice.security.auth.saml.replay_cache import (
    record_response_id,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_STATUS_OK,
    get_recorder,
    reset_for_testing as reset_tracing,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _seed_oidc_state(
        *,
        session,
        state: str,
        nonce: str,
        provider_name: str,
        expires_at: datetime
    ) -> None:
    row = AuthOidcState(
        state=state,
        nonce=nonce,
        pkce_verifier_enc=b"verifier",
        provider_name=provider_name,
        expires_at=expires_at,
        redirect_target="",
    )
    session.add(row)
    session.flush()
    session.commit()
    return


def _setup() -> tuple:
    reset_phase1_runtime()
    reset_tracing()
    _engine, session = build_in_memory_session()
    return _engine, session


# -------------------------------------
# Combined sweep — happy path
# -------------------------------------

def test_sweep_removes_expired_oidc_state_and_stale_saml_replay():
    """
    **Feature: 1-authentication (M3)**
    **Property: sweep_auth_caches deletes every expired
    auth_oidc_state row and every past-horizon
    auth_saml_replay_cache row, returning the per-table
    counts in the report.**
    """
    _engine, session = _setup()
    anchor = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    _seed_oidc_state(
        session=session, state="s-old-1", nonce="n1",
        provider_name="okta",
        expires_at=anchor - timedelta(minutes=10),
    )
    _seed_oidc_state(
        session=session, state="s-old-2", nonce="n2",
        provider_name="okta",
        expires_at=anchor - timedelta(minutes=5),
    )
    _seed_oidc_state(
        session=session, state="s-fresh", nonce="n3",
        provider_name="okta",
        expires_at=anchor + timedelta(minutes=5),
    )
    record_response_id(
        db_session=session,
        response_id="_resp-old-1",
        not_on_or_after=anchor - timedelta(minutes=10),
    )
    record_response_id(
        db_session=session,
        response_id="_resp-old-2",
        not_on_or_after=anchor - timedelta(minutes=1),
    )
    record_response_id(
        db_session=session,
        response_id="_resp-fresh",
        not_on_or_after=anchor + timedelta(minutes=10),
    )

    report = sweep_auth_caches(db_session=session, now=anchor)
    testbase.assert_equal(report.oidc_state_rows_removed, 2)
    testbase.assert_equal(report.saml_replay_rows_removed, 2)
    testbase.assert_equal(report.total_rows_removed(), 4)

    remaining_oidc = (
        session.query(AuthOidcState).all()
    )
    remaining_replay = (
        session.query(AuthSamlReplayCache).all()
    )
    testbase.assert_equal(len(remaining_oidc), 1)
    testbase.assert_equal(remaining_oidc[0].state, "s-fresh")
    testbase.assert_equal(len(remaining_replay), 1)
    testbase.assert_equal(
        remaining_replay[0].response_id, "_resp-fresh",
    )
    return


def test_sweep_returns_zero_counts_on_clean_db():
    """
    **Feature: 1-authentication (M3)**
    **Property: sweep_auth_caches against an empty DB
    returns zero counts and a non-negative duration —
    never raises.**
    """
    _engine, session = _setup()
    report = sweep_auth_caches(db_session=session)
    testbase.assert_equal(report.oidc_state_rows_removed, 0)
    testbase.assert_equal(report.saml_replay_rows_removed, 0)
    testbase.assert_equal(report.total_rows_removed(), 0)
    testbase.assert_equal(report.duration_seconds() >= 0.0, True)
    return


def test_sweep_is_re_entrant_second_call_finds_nothing_new():
    """
    **Feature: 1-authentication (M3)**
    **Property: a second sweep right after the first finds
    zero rows because the first sweep already drained the
    expired set.**
    """
    _engine, session = _setup()
    anchor = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    _seed_oidc_state(
        session=session, state="s-old", nonce="n",
        provider_name="okta",
        expires_at=anchor - timedelta(minutes=5),
    )
    record_response_id(
        db_session=session,
        response_id="_resp-old",
        not_on_or_after=anchor - timedelta(minutes=5),
    )
    first = sweep_auth_caches(db_session=session, now=anchor)
    second = sweep_auth_caches(db_session=session, now=anchor)
    testbase.assert_equal(first.total_rows_removed(), 2)
    testbase.assert_equal(second.total_rows_removed(), 0)
    return


# -------------------------------------
# Trace span emitted
# -------------------------------------

def test_sweep_emits_trace_span_with_per_table_counts():
    """
    **Feature: 1-authentication (M3)**
    **Property: sweep_auth_caches opens a trace span named
    auth.background_sweep with attributes carrying both
    per-table row counts.**
    """
    _engine, session = _setup()
    anchor = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    _seed_oidc_state(
        session=session, state="s-old", nonce="n",
        provider_name="okta",
        expires_at=anchor - timedelta(minutes=5),
    )
    record_response_id(
        db_session=session,
        response_id="_resp-old",
        not_on_or_after=anchor - timedelta(minutes=5),
    )
    sweep_auth_caches(db_session=session, now=anchor)
    spans = get_recorder().list_spans_by_name(
        name=SPAN_AUTH_BACKGROUND_SWEEP,
    )
    testbase.assert_equal(len(spans), 1)
    span = spans[0]
    testbase.assert_equal(span.status, SPAN_STATUS_OK)
    testbase.assert_equal(
        span.attributes["oidc_state_rows_removed"], 1,
    )
    testbase.assert_equal(
        span.attributes["saml_replay_rows_removed"], 1,
    )
    testbase.assert_equal(span.attributes["flow"], "background_sweep")
    return


# -------------------------------------
# Structured log event emitted
# -------------------------------------

class _CapturingHandler(logging.Handler):

    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []
        return

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        return


def test_sweep_emits_auth_background_swept_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: sweep_auth_caches emits the
    auth.background.swept structured log event with the
    per-table counts and the duration so operators can
    surface sweep activity on a dashboard.**
    """
    _engine, session = _setup()
    handler = _CapturingHandler()
    auth_logger = logging.getLogger(LOGGER_NAME)
    auth_logger.setLevel(logging.DEBUG)
    auth_logger.addHandler(handler)
    try:
        sweep_auth_caches(db_session=session)
    finally:
        auth_logger.removeHandler(handler)
    matched = [
        r for r in handler.records
        if r.msg == LOG_EVENT_AUTH_BACKGROUND_SWEPT
    ]
    testbase.assert_equal(len(matched) >= 1, True)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(
        payload["oidc_state_rows_removed"], 0,
    )
    testbase.assert_equal(
        payload["saml_replay_rows_removed"], 0,
    )
    testbase.assert_equal("started_at" in payload, True)
    testbase.assert_equal("ended_at" in payload, True)
    testbase.assert_equal("duration_seconds" in payload, True)
    return


# -------------------------------------
# Validation
# -------------------------------------

def test_sweep_requires_db_session():
    """
    **Feature: 1-authentication (M3)**
    **Property: a None db_session raises ValueError so a
    misconfigured scheduler can't crash silently.**
    """
    _setup()
    raised = False
    try:
        sweep_auth_caches(db_session=None)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_sweep_report_total_and_duration_accessors():
    """
    **Feature: 1-authentication (M3)**
    **Property: SweepReport.total_rows_removed sums the
    per-table counts and duration_seconds returns the
    elapsed seconds between started_at and ended_at.**
    """
    started_at = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(milliseconds=250)
    report = SweepReport(
        oidc_state_rows_removed=3,
        saml_replay_rows_removed=4,
        started_at=started_at,
        ended_at=ended_at,
    )
    testbase.assert_equal(report.total_rows_removed(), 7)
    testbase.assert_equal(report.duration_seconds(), 0.25)
    return
