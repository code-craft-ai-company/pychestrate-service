"""
.. module:: security.auth.session_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Session open/resolve/close API.

.. moduleauthor:: Code Craft AI LLC

Implements the M1 skeleton of :func:`open_session`,
:func:`resolve_session`, and :func:`close_session`. These functions
persist the authoritative ``auth_sessions`` row and publish
``entity.session.*`` events on commit.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event

from ccai.pychestrate.webservice.security.auth.events import AuthEventTopics
from ccai.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind, AuthSession


@dataclass(frozen=True)
class RequestFingerprint:
    """
        Client fingerprint captured at session open for replay-mitigation.

        :param ip_fingerprint: Hash of the remote IP.
        :param user_agent_fingerprint: Hash of the User-Agent header.
    """
    ip_fingerprint: str
    user_agent_fingerprint: str


@dataclass(frozen=True)
class AuthPrincipal:
    """
        Lightweight representation of the authenticated principal on a request.

        :param user_id: Authoritative user id from ``identity_users``.
        :param session_id: The session backing this principal.
        :param provider_kind: Kind of provider that opened the session.
        :param provider_name: Provider name instance.
    """
    user_id: str
    session_id: str
    provider_kind: AuthProviderKind
    provider_name: str


def open_session(
        *,
        db_session: DbSession,
        user_id: str,
        provider_kind: AuthProviderKind,
        provider_name: str,
        mfa_method_name: Optional[str],
        access_token_payload: Optional[bytes],
        refresh_token_payload: Optional[bytes],
        request_fingerprint: RequestFingerprint,
        idle_timeout_seconds: int,
        max_lifetime_seconds: int
    ) -> AuthSession:
    """
        Persist a new session row and publish ``entity.session.opened``.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Authenticated principal id.
        :param provider_kind: OIDC | SAML | LOCAL.
        :param provider_name: Name of the configured provider instance.
        :param mfa_method_name: Method used for 2FA, if any.
        :param access_token_payload: Sealed access-token bytes, if any.
        :param refresh_token_payload: Sealed refresh-token bytes, if any.
        :param request_fingerprint: Fingerprint captured at open time.
        :param idle_timeout_seconds: Inactivity deadline.
        :param max_lifetime_seconds: Absolute ceiling.

        :returns: The persisted :class:`AuthSession`.
    """
    now = utc_now()
    session = AuthSession(
        session_id=new_uuid(),
        user_id=user_id,
        provider_kind=provider_kind,
        provider_name=provider_name,
        opened_at=now,
        expires_at=now + timedelta(seconds=max_lifetime_seconds),
        last_seen_at=now,
        idle_timeout_seconds=idle_timeout_seconds,
        access_token_enc=access_token_payload,
        refresh_token_enc=refresh_token_payload,
        mfa_method_name=mfa_method_name,
        ip_fingerprint=request_fingerprint.ip_fingerprint,
        user_agent_fingerprint=request_fingerprint.user_agent_fingerprint,
    )
    db_session.add(session)
    db_session.flush()

    payload = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "provider_kind": provider_kind.value,
        "provider_name": provider_name,
        "mfa_method_name": mfa_method_name,
        "opened_at": session.opened_at.isoformat(),
    }
    event = EntityEvent(
        topic=AuthEventTopics.SESSION_OPENED,
        payload=payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)
    db_session.commit()

    rtnval = session
    return rtnval


def resolve_session(
        *,
        db_session: DbSession,
        session_id: str,
        now: datetime
    ) -> AuthPrincipal:
    """
        Validate a session id and return an :class:`AuthPrincipal`.

        :param db_session: Active SQLAlchemy session.
        :param session_id: Session id from the cookie.
        :param now: Evaluation timestamp.

        :returns: A populated :class:`AuthPrincipal`.
        :raises: SessionExpiredError, SessionNotFoundError
    """
    session = db_session.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is None:
        err_msg_lines = ["Session resolution failed — session id not found."]
        err_msg_lines.append("SESSION_ID: {}".format(session_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise SessionNotFoundError(err_msg) from None

    if session.expires_at is not None:
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            err_msg_lines = ["Session resolution failed — session expired."]
            err_msg_lines.append("SESSION_ID: {}".format(session_id))
            err_msg_lines.append("EXPIRES_AT: {}".format(session.expires_at.isoformat()))
            err_msg = os.linesep.join(err_msg_lines)
            raise SessionExpiredError(err_msg) from None

    if (session.idle_timeout_seconds is not None
            and session.last_seen_at is not None):
        last_seen_at = session.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
        idle_deadline = last_seen_at + timedelta(
            seconds=int(session.idle_timeout_seconds)
        )
        if idle_deadline <= now:
            err_msg_lines = [
                "Session resolution failed — idle timeout exceeded."
            ]
            err_msg_lines.append("SESSION_ID: {}".format(session_id))
            err_msg_lines.append(
                "LAST_SEEN_AT: {}".format(
                    session.last_seen_at.isoformat()
                )
            )
            err_msg_lines.append(
                "IDLE_TIMEOUT_SECONDS: {}".format(
                    session.idle_timeout_seconds
                )
            )
            err_msg = os.linesep.join(err_msg_lines)
            raise SessionExpiredError(err_msg) from None

    # Activity refreshes the idle window so long-lived interactive
    # sessions stay alive under sustained use.
    session.last_seen_at = now
    db_session.flush()

    rtnval = AuthPrincipal(
        user_id=str(session.user_id),
        session_id=str(session.session_id),
        provider_kind=session.provider_kind,
        provider_name=session.provider_name,
    )
    return rtnval


def close_session(*, db_session: DbSession, session_id: str) -> None:
    """
        Close a session and publish ``entity.session.closed``.

        :param db_session: Active SQLAlchemy session.
        :param session_id: Session id to close.

        :returns: None.
    """
    session = db_session.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is None:
        return

    # Capture payload fields before the delete expires the instance so we
    # do not re-load from the detached row after the commit.
    closed_session_id = str(session.session_id)
    closed_user_id = str(session.user_id)

    payload = {
        "session_id": closed_session_id,
        "user_id": closed_user_id,
        "reason": "user_logout",
        "closed_at": utc_now().isoformat(),
    }
    event = EntityEvent(
        topic=AuthEventTopics.SESSION_CLOSED,
        payload=payload,
        source_event_id=new_uuid(),
    )

    db_session.delete(session)
    enqueue_event(db_session=db_session, event=event)
    db_session.commit()

    return
