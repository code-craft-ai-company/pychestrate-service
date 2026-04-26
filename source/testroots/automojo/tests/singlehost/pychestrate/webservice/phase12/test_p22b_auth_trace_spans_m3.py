"""
.. module:: test_p22b_auth_trace_spans_m3
    :synopsis: Tests for P22b — 1-authentication M3 trace-span seam.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import time

from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_MFA_VERIFY,
    SPAN_NAMES,
    SPAN_OIDC_CALLBACK,
    SPAN_OIDC_REFRESH,
    SPAN_OIDC_TOKEN_EXCHANGE,
    SPAN_SAML_METADATA_REFRESH,
    SPAN_SAML_VALIDATE,
    SPAN_SESSION_RESOLVE,
    SPAN_STATUS_ERROR,
    SPAN_STATUS_OK,
    BufferedSpanRecorder,
    Span,
    SpanRecorder,
    get_recorder,
    reset_for_testing,
    set_recorder,
    start_span,
    traced,
)


# -------------------------------------
# Stable span names cover the spec set
# -------------------------------------

def test_span_names_constant_lists_every_spec_mandated_name():
    """
    **Feature: 1-authentication (M3)**
    **Property: SPAN_NAMES enumerates exactly the seven
    span names the spec calls out: oidc.callback,
    oidc.token_exchange, oidc.refresh, saml.validate,
    saml.metadata_refresh, session.resolve, mfa.verify.**
    """
    expected = sorted([
        "oidc.callback",
        "oidc.token_exchange",
        "oidc.refresh",
        "saml.validate",
        "saml.metadata_refresh",
        "session.resolve",
        "mfa.verify",
    ])
    actual = sorted(SPAN_NAMES)
    testbase.assert_equal(actual, expected)
    # Spot-check the constants too.
    testbase.assert_equal(SPAN_OIDC_CALLBACK, "oidc.callback")
    testbase.assert_equal(SPAN_SAML_VALIDATE, "saml.validate")
    testbase.assert_equal(SPAN_MFA_VERIFY, "mfa.verify")
    return


# -------------------------------------
# start_span happy path
# -------------------------------------

def test_start_span_records_finalized_span_with_name_and_timestamps():
    """
    **Feature: 1-authentication (M3)**
    **Property: start_span emits a Span with started_at /
    ended_at populated and status='ok' after a clean
    body.**
    """
    reset_for_testing()
    with start_span(name=SPAN_OIDC_CALLBACK) as span:
        testbase.assert_equal(span.name, SPAN_OIDC_CALLBACK)
        testbase.assert_equal(span.status, SPAN_STATUS_OK)
        testbase.assert_equal(span.ended_at is None, True)
    recorder = get_recorder()
    spans = recorder.list_spans()
    testbase.assert_equal(len(spans), 1)
    finalized = spans[0]
    testbase.assert_equal(finalized.name, SPAN_OIDC_CALLBACK)
    testbase.assert_equal(finalized.status, SPAN_STATUS_OK)
    testbase.assert_equal(finalized.ended_at is not None, True)
    testbase.assert_equal(
        finalized.ended_at >= finalized.started_at, True,
    )
    return


def test_start_span_records_initial_attributes_and_set_attribute():
    """
    **Feature: 1-authentication (M3)**
    **Property: start_span carries caller-supplied initial
    attributes; Span.set_attribute lets the body annotate
    the live span (provider_name, outcome, etc.) before
    finalization.**
    """
    reset_for_testing()
    with start_span(
        name=SPAN_OIDC_CALLBACK,
        attributes={"provider_name": "okta"},
    ) as span:
        span.set_attribute(key="outcome", value="provisioned")
        span.set_attribute(key="user_id", value="u1")
    recorder = get_recorder()
    finalized = recorder.list_spans()[0]
    testbase.assert_equal(
        finalized.attributes["provider_name"], "okta",
    )
    testbase.assert_equal(
        finalized.attributes["outcome"], "provisioned",
    )
    testbase.assert_equal(finalized.attributes["user_id"], "u1")
    return


def test_start_span_duration_seconds_reports_elapsed_time():
    """
    **Feature: 1-authentication (M3)**
    **Property: Span.duration_seconds returns the elapsed
    seconds between started_at and ended_at after the
    span finalizes.**
    """
    reset_for_testing()
    with start_span(name=SPAN_OIDC_TOKEN_EXCHANGE):
        time.sleep(0.01)
    span = get_recorder().list_spans()[0]
    elapsed = span.duration_seconds()
    testbase.assert_equal(elapsed is not None, True)
    testbase.assert_equal(elapsed >= 0.005, True)
    return


# -------------------------------------
# Exception path
# -------------------------------------

class _StubReasonError(Exception):
    """Carries a stable reason attribute like the M2 errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        return


def test_start_span_marks_status_error_and_captures_reason_token():
    """
    **Feature: 1-authentication (M3)**
    **Property: when the body raises an exception that
    carries a stable reason attribute (the M2 auth error
    pattern), the span status flips to 'error' and the
    reason token rides on the finalized span.**
    """
    reset_for_testing()
    raised = False
    try:
        with start_span(name=SPAN_OIDC_REFRESH):
            raise _StubReasonError(reason="token_refresh_failed")
    except _StubReasonError:
        raised = True
    testbase.assert_equal(raised, True)
    span = get_recorder().list_spans()[0]
    testbase.assert_equal(span.status, SPAN_STATUS_ERROR)
    testbase.assert_equal(
        span.exception_reason, "token_refresh_failed",
    )
    testbase.assert_equal(span.ended_at is not None, True)
    return


def test_start_span_falls_back_to_class_name_when_no_reason_attr():
    """
    **Feature: 1-authentication (M3)**
    **Property: a plain exception with no reason attribute
    surfaces its class name as exception_reason so
    debuggers still get a useful tag.**
    """
    reset_for_testing()
    try:
        with start_span(name=SPAN_SESSION_RESOLVE):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    span = get_recorder().list_spans()[0]
    testbase.assert_equal(span.status, SPAN_STATUS_ERROR)
    testbase.assert_equal(span.exception_reason, "RuntimeError")
    return


def test_start_span_bubbles_exception_unchanged():
    """
    **Feature: 1-authentication (M3)**
    **Property: the exception propagates unchanged after
    the span finalizes — no swallowing, no wrapping.**
    """
    reset_for_testing()
    captured = None
    try:
        with start_span(name=SPAN_SAML_VALIDATE):
            raise ValueError("specific-message")
    except ValueError as err:
        captured = err
    testbase.assert_equal(captured is not None, True)
    testbase.assert_equal(str(captured), "specific-message")
    return


# -------------------------------------
# Recorder management
# -------------------------------------

def test_set_recorder_replaces_process_level_recorder():
    """
    **Feature: 1-authentication (M3)**
    **Property: set_recorder swaps in a caller-supplied
    SpanRecorder; subsequent start_span calls record
    against it.**
    """
    custom = BufferedSpanRecorder()
    set_recorder(recorder=custom)
    with start_span(name=SPAN_MFA_VERIFY):
        pass
    testbase.assert_equal(len(custom.list_spans()), 1)
    testbase.assert_equal(get_recorder() is custom, True)
    return


def test_reset_for_testing_swaps_in_fresh_recorder():
    """
    **Feature: 1-authentication (M3)**
    **Property: reset_for_testing replaces the active
    recorder with a fresh BufferedSpanRecorder so cross-
    test span buffers can't leak.**
    """
    with start_span(name=SPAN_OIDC_CALLBACK):
        pass
    pre_reset = get_recorder()
    reset_for_testing()
    post_reset = get_recorder()
    testbase.assert_equal(pre_reset is not post_reset, True)
    testbase.assert_equal(post_reset.list_spans(), [])
    return


def test_set_recorder_rejects_none():
    """
    **Feature: 1-authentication (M3)**
    **Property: set_recorder(recorder=None) raises
    ValueError so callers can't accidentally null out the
    recorder.**
    """
    raised = False
    try:
        set_recorder(recorder=None)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_buffered_recorder_filters_by_name():
    """
    **Feature: 1-authentication (M3)**
    **Property: BufferedSpanRecorder.list_spans_by_name
    returns only spans matching the supplied name —
    convenience for tests.**
    """
    reset_for_testing()
    with start_span(name=SPAN_OIDC_CALLBACK):
        pass
    with start_span(name=SPAN_SAML_VALIDATE):
        pass
    with start_span(name=SPAN_OIDC_CALLBACK):
        pass
    recorder = get_recorder()
    callback_spans = recorder.list_spans_by_name(
        name=SPAN_OIDC_CALLBACK,
    )
    saml_spans = recorder.list_spans_by_name(
        name=SPAN_SAML_VALIDATE,
    )
    testbase.assert_equal(len(callback_spans), 2)
    testbase.assert_equal(len(saml_spans), 1)
    return


def test_buffered_recorder_reset_drops_every_span():
    """
    **Feature: 1-authentication (M3)**
    **Property: BufferedSpanRecorder.reset clears the
    buffer in place without swapping the recorder.**
    """
    custom = BufferedSpanRecorder()
    set_recorder(recorder=custom)
    with start_span(name=SPAN_SAML_METADATA_REFRESH):
        pass
    testbase.assert_equal(len(custom.list_spans()), 1)
    custom.reset()
    testbase.assert_equal(custom.list_spans(), [])
    return


# -------------------------------------
# traced decorator
# -------------------------------------

def test_traced_decorator_wraps_function_in_span():
    """
    **Feature: 1-authentication (M3)**
    **Property: @traced decorates a function so each call
    runs inside a span; the function's return value is
    passed through unchanged.**
    """
    reset_for_testing()

    @traced(name=SPAN_OIDC_TOKEN_EXCHANGE)
    def _exchange(value: int) -> int:
        return value * 2

    result = _exchange(7)
    testbase.assert_equal(result, 14)
    spans = get_recorder().list_spans()
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].name, SPAN_OIDC_TOKEN_EXCHANGE)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    return


def test_traced_decorator_marks_error_on_raise():
    """
    **Feature: 1-authentication (M3)**
    **Property: when the decorated function raises, the
    span is finalized with status='error' and the
    exception bubbles unchanged.**
    """
    reset_for_testing()

    @traced(name=SPAN_MFA_VERIFY)
    def _verify():
        raise _StubReasonError(reason="code_invalid")

    raised = False
    try:
        _verify()
    except _StubReasonError:
        raised = True
    testbase.assert_equal(raised, True)
    span = get_recorder().list_spans()[0]
    testbase.assert_equal(span.status, SPAN_STATUS_ERROR)
    testbase.assert_equal(span.exception_reason, "code_invalid")
    return


# -------------------------------------
# Validation
# -------------------------------------

def test_start_span_rejects_empty_name():
    """
    **Feature: 1-authentication (M3)**
    **Property: start_span raises ValueError for empty /
    None names so callers can't smuggle an unlabeled
    span into the recorder.**
    """
    raised_empty = False
    try:
        with start_span(name=""):
            pass
    except ValueError:
        raised_empty = True
    testbase.assert_equal(raised_empty, True)
    return


def test_set_attribute_rejects_empty_key():
    """
    **Feature: 1-authentication (M3)**
    **Property: Span.set_attribute raises ValueError on
    empty keys.**
    """
    reset_for_testing()
    raised = False
    try:
        with start_span(name=SPAN_SESSION_RESOLVE) as span:
            span.set_attribute(key="", value="x")
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_default_recorder_is_buffered_span_recorder():
    """
    **Feature: 1-authentication (M3)**
    **Property: the module-level recorder defaults to a
    BufferedSpanRecorder so the auth flows always have
    something to record into without bootstrap wiring.**
    """
    reset_for_testing()
    recorder = get_recorder()
    testbase.assert_equal(
        isinstance(recorder, BufferedSpanRecorder), True,
    )
    return
