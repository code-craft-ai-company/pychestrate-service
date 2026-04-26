"""
.. module:: security.auth.tracing
    :synopsis: Auth trace-span seam (M3 T3.3).

The 1-authentication M3 hardening pass mandates trace
spans on every named flow: ``oidc.callback``,
``oidc.token_exchange``, ``oidc.refresh``,
``saml.validate``, ``saml.metadata_refresh``,
``session.resolve``, and ``mfa.verify``. This module ships
a pluggable trace seam so production deployments can wire
OpenTelemetry / Datadog / Jaeger and tests / dev can use
the in-memory :class:`BufferedSpanRecorder` to assert that
spans were emitted with the right name + attributes.

The seam intentionally stays small — five primitives:

* :class:`Span` — frozen dataclass holding the span name,
  start/end timestamps, attributes, status, and the
  exception reason when the body raised.
* :func:`start_span` — context-manager that builds the
  span, runs the caller's body, captures any exception,
  hands the finalized span to the recorder on exit.
* :func:`set_recorder` / :func:`reset_for_testing` —
  process-level recorder management.
* :class:`SpanRecorder` — abstract recorder protocol.
* :class:`BufferedSpanRecorder` — in-memory recorder used
  by tests and the M3 dev mode.

The default recorder is :class:`BufferedSpanRecorder` so
the auth flows always have something to record into;
production overrides via :func:`set_recorder` once the
OTel exporter is wired.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import contextlib
import functools
import os
import threading

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any, Callable, Dict, Generator, List, Mapping, Optional,
)


# Stable span names — exactly the seven the spec calls out.
SPAN_OIDC_CALLBACK: str = "oidc.callback"
SPAN_OIDC_TOKEN_EXCHANGE: str = "oidc.token_exchange"
SPAN_OIDC_REFRESH: str = "oidc.refresh"
SPAN_SAML_VALIDATE: str = "saml.validate"
SPAN_SAML_METADATA_REFRESH: str = "saml.metadata_refresh"
SPAN_SESSION_RESOLVE: str = "session.resolve"
SPAN_MFA_VERIFY: str = "mfa.verify"


SPAN_NAMES: tuple = (
    SPAN_OIDC_CALLBACK,
    SPAN_OIDC_TOKEN_EXCHANGE,
    SPAN_OIDC_REFRESH,
    SPAN_SAML_VALIDATE,
    SPAN_SAML_METADATA_REFRESH,
    SPAN_SESSION_RESOLVE,
    SPAN_MFA_VERIFY,
)


SPAN_STATUS_OK: str = "ok"
SPAN_STATUS_ERROR: str = "error"


@dataclass
class Span:
    """
        Mutable span record. Mutable so the context manager
        can stamp ``ended_at`` / ``status`` /
        ``exception_reason`` on exit before handing the
        finalized record to the recorder.

        :param name: Stable span name (one of
                     :data:`SPAN_NAMES` for auth spans;
                     callers can use any string).
        :param started_at: tz-aware UTC timestamp captured
                           on context-manager entry.
        :param ended_at: tz-aware UTC timestamp captured on
                         context-manager exit; ``None``
                         until then.
        :param attributes: Per-span key/value attribute set;
                           ``set_attribute`` on the live
                           span lets the body annotate the
                           span as it progresses.
        :param status: ``"ok"`` on a clean exit;
                       ``"error"`` when the body raised.
        :param exception_reason: When the body raised an
                                 exception with a stable
                                 ``reason`` token (e.g.
                                 :class:`OidcCallbackError`),
                                 that token lands here.
                                 Plain exceptions land
                                 the type name.
    """
    name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = SPAN_STATUS_OK
    exception_reason: Optional[str] = None

    def set_attribute(self, *, key: str, value: Any) -> None:
        """
            Annotate the live span with a single key/value.
            The body inside :func:`start_span` calls this to
            record decisions ("provider_kind=OIDC",
            "outcome=refreshed", etc.).
        """
        if key is None or len(key) == 0:
            err_lines = ["Span.set_attribute requires a non-empty key."]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        self.attributes[key] = value
        return

    def duration_seconds(self) -> Optional[float]:
        """
            Convenience accessor — ``None`` when the span
            hasn't ended yet, else the elapsed seconds.
        """
        if self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        rtnval = delta.total_seconds()
        return rtnval


class SpanRecorder:
    """
        Recorder protocol. Production deployments wire an
        adapter that forwards finalized spans to an OTel /
        Datadog / Jaeger exporter; the in-tree
        :class:`BufferedSpanRecorder` keeps spans in a
        list for tests + dev introspection.
    """

    def record(self, *, span: Span) -> None:
        """
            Persist a finalized span. Called once per
            span by :func:`start_span` on context-manager
            exit.
        """
        err_lines = ["Subclasses must implement SpanRecorder.record."]
        err_msg = os.linesep.join(err_lines)
        raise NotImplementedError(err_msg)


class BufferedSpanRecorder(SpanRecorder):
    """
        In-memory :class:`SpanRecorder` that stores every
        finalized span in a list. Test-only / dev-only
        seam; production wires an actual exporter.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._spans: List[Span] = []
        return

    def record(self, *, span: Span) -> None:
        with self._lock:
            self._spans.append(span)
        return

    def list_spans(self) -> List[Span]:
        """
            Snapshot of every span recorded so far.
        """
        with self._lock:
            rtnval = list(self._spans)
        return rtnval

    def list_spans_by_name(self, *, name: str) -> List[Span]:
        """
            Filtered snapshot — spans whose ``name``
            matches.
        """
        with self._lock:
            matched = [s for s in self._spans if s.name == name]
        rtnval = matched
        return rtnval

    def reset(self) -> None:
        """
            Drop every buffered span.
        """
        with self._lock:
            self._spans.clear()
        return


_GUARD: threading.RLock = threading.RLock()
_RECORDER: SpanRecorder = BufferedSpanRecorder()


def set_recorder(*, recorder: SpanRecorder) -> None:
    """
        Replace the process-level recorder. Production
        bootstrap calls this once at startup with the OTel
        adapter; tests typically swap in a fresh
        :class:`BufferedSpanRecorder` per case.
    """
    if recorder is None:
        err_lines = ["set_recorder requires a non-None SpanRecorder."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    global _RECORDER
    with _GUARD:
        _RECORDER = recorder
    return


def get_recorder() -> SpanRecorder:
    """
        Return the active recorder. Mostly used by tests
        to assert against a known
        :class:`BufferedSpanRecorder` instance.
    """
    with _GUARD:
        rtnval = _RECORDER
    return rtnval


def reset_for_testing() -> None:
    """
        Replace the active recorder with a fresh
        :class:`BufferedSpanRecorder` so tests start each
        case on an empty buffer.
    """
    set_recorder(recorder=BufferedSpanRecorder())
    return


@contextlib.contextmanager
def start_span(
        *,
        name: str,
        attributes: Optional[Mapping[str, Any]] = None
    ) -> Generator[Span, None, None]:
    """
        Open a span around the ``with`` body. Captures
        ``started_at`` on entry, runs the body, captures
        ``ended_at`` on exit, and hands the finalized
        :class:`Span` to the active recorder. When the body
        raises, the span's ``status`` flips to
        :data:`SPAN_STATUS_ERROR` and
        ``exception_reason`` is set to either the
        exception's ``reason`` attribute (when present —
        every M2 auth error type carries one) or the
        exception's class name; the exception then
        bubbles unchanged.

        :param name: Stable span name.
        :param attributes: Optional initial attributes.

        :yields: The live :class:`Span` instance — the body
                 can call :meth:`Span.set_attribute` on it.
    """
    if name is None or len(name) == 0:
        err_lines = ["start_span requires a non-empty name."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    materialized_attributes: Dict[str, Any] = {}
    if attributes is not None:
        for key, value in attributes.items():
            materialized_attributes[key] = value
    span = Span(
        name=name,
        started_at=_now_utc(),
        attributes=materialized_attributes,
    )
    try:
        yield span
    except BaseException as err:
        span.status = SPAN_STATUS_ERROR
        span.exception_reason = _resolve_exception_reason(exc=err)
        span.ended_at = _now_utc()
        get_recorder().record(span=span)
        raise
    else:
        span.ended_at = _now_utc()
        get_recorder().record(span=span)
    return


def traced(
        *,
        name: str,
        attributes: Optional[Mapping[str, Any]] = None
    ):
    """
        Decorator equivalent of :func:`start_span`. The
        wrapped function runs inside the span; the live
        :class:`Span` instance isn't passed to the function
        body — for callers that need to annotate the span
        from inside, use :func:`start_span` directly.
    """
    def _decorator(fn: Callable):
        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            with start_span(name=name, attributes=attributes):
                rtnval = fn(*args, **kwargs)
            return rtnval
        return _wrapper
    return _decorator


def _resolve_exception_reason(*, exc: BaseException) -> str:
    # Every M2 auth error carries a stable .reason attr
    # (OidcCallbackError, OidcRefreshError,
    # IdTokenValidationError, TokenExchangeError,
    # SamlMetadataParseError, SamlAssertionValidationError,
    # ClaimsMissingError -> via subclass). When present we
    # surface that token on the span; otherwise we fall
    # back to the exception class name.
    reason = getattr(exc, "reason", None)
    if reason is None or not isinstance(reason, str) or len(reason) == 0:
        rtnval = type(exc).__name__
        return rtnval
    rtnval = reason
    return rtnval


def _now_utc() -> datetime:
    rtnval = datetime.now(tz=timezone.utc)
    return rtnval
