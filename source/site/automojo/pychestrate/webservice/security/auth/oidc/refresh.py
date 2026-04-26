"""
.. module:: security.auth.oidc.refresh
    :synopsis: OIDC refresh-token rotation with single-flight collapse.

The middleware on a hot-path request detects an
``auth_sessions`` row whose ``expires_at`` is within
``DEFAULT_REFRESH_LEEWAY_SECONDS`` of ``now`` and calls
:func:`refresh_oidc_session` to rotate the access (and
optionally the refresh) token through the IdP's token
endpoint.

Single-flight collapse: a per-session ``threading.Lock``
serializes concurrent refreshes for the same ``session_id``
so only one thread hits the IdP. Threads that wait on the
lock then re-read the session row and skip the refresh when
the row has already been pushed past the leeway window —
that is the "collapse" the spec calls out.

The actual HTTP POST to the token endpoint is pluggable so
production wires ``urllib`` and tests pass a deterministic
stub (mirroring the P18a token-exchange seam).

The session row's absolute ceiling ``opened_at +
max_lifetime_seconds`` is enforced: a refresh that would
push ``expires_at`` past that ceiling lands the row exactly
at the ceiling instead, so a long-running session can't be
rolled forever.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event

from automojo.pychestrate.webservice.security.auth.events import AuthEventTopics
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeRawResponse,
)
from automojo.pychestrate.webservice.security.auth import (
    log_events,
    metrics_emitter,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_OIDC_REFRESH,
    start_span,
)


DEFAULT_REFRESH_LEEWAY_SECONDS: int = 60
DEFAULT_EXTENSION_SECONDS: int = 3600
DEFAULT_MAX_LIFETIME_SECONDS: int = 8 * 3600


@dataclass(frozen=True)
class TokenRefreshRequest:
    """
        Inputs the refresh fetcher consumes when posting to
        the IdP's token endpoint with
        ``grant_type=refresh_token``.

        :param token_endpoint: IdP token endpoint URL.
        :param client_id: OIDC client id.
        :param refresh_token: Current refresh token recovered
                              from the session row.
        :param client_secret: Optional secret for confidential
                              clients.
        :param scope: Optional scope override; ``None`` lets
                      the IdP fall back to the original
                      grant's scope.
    """
    token_endpoint: str
    client_id: str
    refresh_token: str
    client_secret: Optional[str] = None
    scope: Optional[str] = None


TokenRefreshFetcher = Callable[
    [TokenRefreshRequest], "TokenExchangeRawResponse",
]


class OidcRefreshError(Exception):
    """
        Raised when :func:`refresh_oidc_session` fails. The
        ``reason`` token is stable so callers can branch
        without parsing the detail string.

        Reasons:

        * ``session_not_found`` — no ``auth_sessions`` row
          matched the supplied id.
        * ``provider_kind_mismatch`` — the row exists but
          belongs to a non-OIDC provider.
        * ``missing_refresh_token`` — the row has no
          ``refresh_token_enc`` to refresh against.
        * ``token_refresh_failed`` — the IdP returned a non-2xx
          status, an ``error`` field, or a malformed payload.
    """

    def __init__(
            self,
            reason: str,
            detail: str = "",
            cause: Optional[str] = None
        ) -> None:
        message = (
            reason if len(detail) == 0
            else "{}: {}".format(reason, detail)
        )
        super().__init__(message)
        self.reason: str = reason
        self.detail: str = detail
        self.cause: Optional[str] = cause
        return


@dataclass(frozen=True)
class OidcRefreshResult:
    """
        Outcome of :func:`refresh_oidc_session`.

        :param session: The refreshed (or skipped)
                        :class:`AuthSession` row.
        :param outcome: ``"refreshed"`` when the IdP was
                        called and the row was updated;
                        ``"skipped_fresh"`` when single-flight
                        collapse saw the row already past the
                        leeway window.
        :param refresh_token_rotated: ``True`` when the IdP
                                      returned a new refresh
                                      token and the row was
                                      updated to carry it;
                                      ``False`` otherwise (the
                                      original refresh token
                                      stayed in place).
        :param previous_expires_at: ``expires_at`` value
                                    before the refresh — kept
                                    so callers can log how far
                                    the row was rolled.
    """
    session: AuthSession
    outcome: str
    refresh_token_rotated: bool
    previous_expires_at: datetime


class _PerSessionLocker:
    """
        Process-local locker keyed on ``session_id`` so
        concurrent refreshes for the same session collapse
        onto a single IdP call.

        The implementation keeps one
        :class:`threading.Lock` per active session id; entries
        are pruned by :meth:`reset_for_testing`. For
        multi-process deployments callers can pass a custom
        :class:`SingleFlightLockerProtocol` implementation
        backed by a Postgres advisory lock or Redis.
    """

    def __init__(self) -> None:
        self._guard: threading.Lock = threading.Lock()
        self._locks: Dict[str, threading.Lock] = {}
        return

    def acquire(self, *, session_id: str) -> threading.Lock:
        """
            Return the per-session lock instance, creating
            it on first call.
        """
        with self._guard:
            existing = self._locks.get(session_id)
            if existing is None:
                existing = threading.Lock()
                self._locks[session_id] = existing
        rtnval = existing
        return rtnval

    def reset_for_testing(self) -> None:
        """
            Drop every cached per-session lock.
        """
        with self._guard:
            self._locks.clear()
        return


SingleFlightLocker = _PerSessionLocker
DEFAULT_LOCKER: _PerSessionLocker = _PerSessionLocker()


def refresh_oidc_session(
        *,
        db_session: DbSession,
        session_id: str,
        token_endpoint: str,
        client_id: str,
        token_fetcher: TokenRefreshFetcher,
        client_secret: Optional[str] = None,
        scope: Optional[str] = None,
        refresh_leeway_seconds: int = DEFAULT_REFRESH_LEEWAY_SECONDS,
        extension_seconds: int = DEFAULT_EXTENSION_SECONDS,
        max_lifetime_seconds: int = DEFAULT_MAX_LIFETIME_SECONDS,
        locker: Optional[_PerSessionLocker] = None,
        now: Optional[datetime] = None
    ) -> OidcRefreshResult:
    """
        Rotate the access (and optionally the refresh) token
        for an OIDC-backed session.

        :param db_session: Active SQLAlchemy session.
        :param session_id: ``auth_sessions.session_id`` of the
                           row to refresh.
        :param token_endpoint: IdP token endpoint URL.
        :param client_id: OIDC client id.
        :param token_fetcher: Pluggable callable that performs
                              the HTTP POST to the token
                              endpoint.
        :param client_secret: Optional confidential-client
                              secret.
        :param scope: Optional scope override forwarded to the
                      IdP.
        :param refresh_leeway_seconds: How close to
                                       ``expires_at`` the row
                                       has to be before a
                                       refresh fires;
                                       ``"skipped_fresh"`` is
                                       returned when the row
                                       still has more headroom
                                       than this. Default
                                       ``60``.
        :param extension_seconds: How far to push
                                  ``expires_at`` on a
                                  successful refresh. Default
                                  ``3600``.
        :param max_lifetime_seconds: Absolute ceiling enforced
                                     against ``opened_at``. A
                                     refresh that would push
                                     past the ceiling lands
                                     the row at the ceiling.
                                     Default ``8 * 3600``.
        :param locker: Optional single-flight locker
                       implementation; ``None`` uses the
                       module-level
                       :data:`DEFAULT_LOCKER`.
        :param now: Optional clock override (test seam).

        :returns: :class:`OidcRefreshResult`.
        :raises: OidcRefreshError with a stable ``reason``
                 token; ValueError on missing required inputs.
    """
    if db_session is None:
        err_lines = ["refresh_oidc_session requires a db_session."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if session_id is None or len(str(session_id)) == 0:
        err_lines = ["refresh_oidc_session requires a session_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if token_endpoint is None or len(token_endpoint) == 0:
        err_lines = ["refresh_oidc_session requires a token_endpoint."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if client_id is None or len(client_id) == 0:
        err_lines = ["refresh_oidc_session requires a client_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if token_fetcher is None:
        err_lines = ["refresh_oidc_session requires a token_fetcher."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    materialized_locker = locker if locker is not None else DEFAULT_LOCKER
    materialized_now = now if now is not None else utc_now()
    lock = materialized_locker.acquire(session_id=str(session_id))
    with lock:
        with start_span(
            name=SPAN_OIDC_REFRESH,
            attributes={"session_id": str(session_id)},
        ) as span:
            try:
                rtnval = _refresh_inside_lock(
                    db_session=db_session,
                    session_id=str(session_id),
                    token_endpoint=token_endpoint,
                    client_id=client_id,
                    token_fetcher=token_fetcher,
                    client_secret=client_secret,
                    scope=scope,
                    refresh_leeway_seconds=refresh_leeway_seconds,
                    extension_seconds=extension_seconds,
                    max_lifetime_seconds=max_lifetime_seconds,
                    now=materialized_now,
                )
            except Exception:
                metrics_emitter.record_token_refresh(
                    db_session=db_session,
                    outcome=metrics_emitter.TOKEN_REFRESH_OUTCOME_FAILED,
                )
                raise
            span.set_attribute(
                key="outcome", value=rtnval.outcome,
            )
            span.set_attribute(
                key="refresh_token_rotated",
                value=rtnval.refresh_token_rotated,
            )
            metrics_emitter.record_token_refresh(
                db_session=db_session,
                outcome=rtnval.outcome,
            )
            if rtnval.outcome == "refreshed":
                log_events.emit_log_event(
                    event_name=log_events.AUTH_SESSION_REFRESHED,
                    payload={
                        "session_id": str(rtnval.session.session_id),
                        "user_id": str(rtnval.session.user_id),
                        "refresh_token_rotated": rtnval.refresh_token_rotated,
                        "previous_expires_at": rtnval.previous_expires_at.isoformat(),
                        "new_expires_at": rtnval.session.expires_at.isoformat()
                            if rtnval.session.expires_at is not None else None,
                    },
                )
    return rtnval


def _refresh_inside_lock(
        *,
        db_session: DbSession,
        session_id: str,
        token_endpoint: str,
        client_id: str,
        token_fetcher: TokenRefreshFetcher,
        client_secret: Optional[str],
        scope: Optional[str],
        refresh_leeway_seconds: int,
        extension_seconds: int,
        max_lifetime_seconds: int,
        now: datetime
    ) -> OidcRefreshResult:
    session = (
        db_session.query(AuthSession)
        .filter(AuthSession.session_id == session_id)
        .first()
    )
    if session is None:
        raise OidcRefreshError(
            "session_not_found",
            "no auth_sessions row matched session_id={}".format(session_id),
        ) from None
    if session.provider_kind != AuthProviderKind.OIDC:
        raise OidcRefreshError(
            "provider_kind_mismatch",
            "expected OIDC, got {!r}".format(session.provider_kind),
        ) from None

    previous_expires_at = _normalize_aware(value=session.expires_at)
    leeway_threshold = now + timedelta(seconds=refresh_leeway_seconds)
    if previous_expires_at > leeway_threshold:
        # Single-flight collapse: another thread already
        # rolled this row past the leeway window. Skip the
        # IdP call and return the fresh row.
        rtnval = OidcRefreshResult(
            session=session,
            outcome="skipped_fresh",
            refresh_token_rotated=False,
            previous_expires_at=previous_expires_at,
        )
        return rtnval

    if session.refresh_token_enc is None or len(session.refresh_token_enc) == 0:
        raise OidcRefreshError(
            "missing_refresh_token",
            "session has no refresh_token_enc to rotate",
        ) from None

    request = TokenRefreshRequest(
        token_endpoint=token_endpoint,
        client_id=client_id,
        refresh_token=bytes(session.refresh_token_enc).decode("utf-8"),
        client_secret=client_secret,
        scope=scope,
    )
    raw = token_fetcher(request)
    parsed = _parse_refresh_response(raw=raw)

    new_expires_at = _bounded_expires_at(
        opened_at=_normalize_aware(value=session.opened_at),
        proposed=now + timedelta(seconds=extension_seconds),
        max_lifetime_seconds=max_lifetime_seconds,
    )
    rotated = False
    if parsed.refresh_token is not None and len(parsed.refresh_token) > 0:
        session.refresh_token_enc = parsed.refresh_token.encode("utf-8")
        rotated = True
    if parsed.access_token is not None and len(parsed.access_token) > 0:
        session.access_token_enc = parsed.access_token.encode("utf-8")
    session.last_seen_at = now
    session.expires_at = new_expires_at
    db_session.flush()

    payload = {
        "session_id": str(session.session_id),
        "user_id": str(session.user_id),
        "provider_kind": session.provider_kind.value,
        "provider_name": session.provider_name,
        "refreshed_at": now.isoformat(),
        "previous_expires_at": previous_expires_at.isoformat(),
        "new_expires_at": new_expires_at.isoformat(),
        "refresh_token_rotated": rotated,
    }
    event = EntityEvent(
        topic=AuthEventTopics.SESSION_REFRESHED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)
    db_session.commit()

    rtnval = OidcRefreshResult(
        session=session,
        outcome="refreshed",
        refresh_token_rotated=rotated,
        previous_expires_at=previous_expires_at,
    )
    return rtnval


@dataclass(frozen=True)
class _ParsedRefreshResponse:
    access_token: Optional[str]
    refresh_token: Optional[str]
    expires_in_seconds: Optional[int]


def _parse_refresh_response(
        *, raw: Optional[TokenExchangeRawResponse]
    ) -> _ParsedRefreshResponse:
    if raw is None:
        raise OidcRefreshError(
            "token_refresh_failed", "fetcher returned None",
        ) from None
    if raw.status_code < 200 or raw.status_code >= 300:
        provider_error = ""
        if isinstance(raw.payload, dict):
            provider_error = str(raw.payload.get("error", ""))
        raise OidcRefreshError(
            "token_refresh_failed",
            "status={} provider_error={!r}".format(
                raw.status_code, provider_error,
            ),
            cause="http_error",
        ) from None
    if not isinstance(raw.payload, dict):
        raise OidcRefreshError(
            "token_refresh_failed",
            "payload is not an object",
            cause="payload_invalid",
        ) from None
    if "error" in raw.payload:
        raise OidcRefreshError(
            "token_refresh_failed",
            "{}: {}".format(
                raw.payload.get("error"),
                raw.payload.get("error_description", ""),
            ),
            cause="provider_rejected",
        ) from None
    access_token = raw.payload.get("access_token")
    if access_token is not None and not isinstance(access_token, str):
        raise OidcRefreshError(
            "token_refresh_failed",
            "access_token must be a string",
            cause="payload_invalid",
        ) from None
    refresh_token = raw.payload.get("refresh_token")
    if refresh_token is not None and not isinstance(refresh_token, str):
        raise OidcRefreshError(
            "token_refresh_failed",
            "refresh_token must be a string",
            cause="payload_invalid",
        ) from None
    expires_in = raw.payload.get("expires_in")
    expires_in_seconds: Optional[int] = None
    if expires_in is not None:
        try:
            expires_in_seconds = int(expires_in)
        except (TypeError, ValueError):
            raise OidcRefreshError(
                "token_refresh_failed",
                "expires_in not an integer",
                cause="payload_invalid",
            ) from None
    rtnval = _ParsedRefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in_seconds,
    )
    return rtnval


def _bounded_expires_at(
        *,
        opened_at: datetime,
        proposed: datetime,
        max_lifetime_seconds: int
    ) -> datetime:
    ceiling = opened_at + timedelta(seconds=max_lifetime_seconds)
    if proposed > ceiling:
        rtnval = ceiling
        return rtnval
    rtnval = proposed
    return rtnval


def _normalize_aware(*, value: datetime) -> datetime:
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    rtnval = value
    return rtnval
