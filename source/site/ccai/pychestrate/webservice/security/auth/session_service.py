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
from ccai.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
    AuthSession,
    AuthSessionClient,
)


@dataclass(frozen=True)
class RequestFingerprint:
    """
        Client fingerprint captured at session open for replay-mitigation,
        plus the readable client details the admin sessions page shows.

        :param ip_fingerprint: Hash of the remote IP.
        :param user_agent_fingerprint: Hash of the User-Agent header.
        :param client_address: The client's address (resolved behind
                               trusted proxies), when known.
        :param user_agent: The User-Agent header, when known.
    """
    ip_fingerprint: str
    user_agent_fingerprint: str
    client_address: Optional[str] = None
    user_agent: Optional[str] = None


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

    client_address = _bounded_text(value=request_fingerprint.client_address, limit=64)
    user_agent = _bounded_text(value=request_fingerprint.user_agent, limit=512)
    if client_address is not None or user_agent is not None:
        db_session.add(AuthSessionClient(
            session_id=session.session_id,
            client_address=client_address,
            user_agent=user_agent,
        ))
        db_session.flush()

    payload = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "provider_kind": provider_kind.value,
        "provider_name": provider_name,
        "mfa_method_name": mfa_method_name,
        "opened_at": session.opened_at.isoformat(),
        "client_address": client_address,
        "user_agent": _describe_user_agent(user_agent=user_agent),
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


def _bounded_text(*, value: Optional[str], limit: int) -> Optional[str]:
    """
        ``value`` stripped and cut to ``limit`` characters; None when
        empty.
    """
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 0:
        return None
    rtnval = text[:limit]
    return rtnval


def _describe_user_agent(*, user_agent: Optional[str]) -> Optional[str]:
    """
        A readable browser / OS summary for the audit record.
    """
    if user_agent is None:
        return None
    from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
        describe_user_agent,
    )
    rtnval = describe_user_agent(user_agent=user_agent)
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

    # A session only carries the rights of an account that can still
    # sign in. Deactivation closes the account's sessions
    # (:func:`close_sessions_for_user`); this check also refuses any
    # session that outlived its account's status change.
    if _user_can_hold_session(db_session=db_session, user_id=session.user_id) is False:
        err_msg_lines = [
            "Session resolution failed — the account is not active."
        ]
        err_msg_lines.append("SESSION_ID: {}".format(session_id))
        err_msg_lines.append("USER_ID: {}".format(session.user_id))
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


def _user_can_hold_session(*, db_session: DbSession, user_id: object) -> bool:
    """
        Whether the identity user behind a session may still use it.
        Only ``ACTIVE`` accounts may; a missing identity row counts as
        not active (fail closed).

        :param db_session: Active SQLAlchemy session.
        :param user_id: The session's ``user_id``.

        :returns: ``True`` when the account is active.
    """
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
        UserStatus,
    )
    status = (
        db_session.query(IdentityUser.status)
        .filter(IdentityUser.user_id == user_id)
        .scalar()
    )
    rtnval = status == UserStatus.ACTIVE
    return rtnval


def close_sessions_for_user(
        *,
        db_session: DbSession,
        user_id: object,
        reason: str,
        actor_user_id: Optional[str] = None,
        keep_session_id: Optional[str] = None
    ) -> int:
    """
        Close every open session belonging to ``user_id`` and publish
        ``entity.session.closed`` for each, without committing: the
        caller commits, so the closure lands in the same transaction
        as the change that required it (for example deactivation).

        :param db_session: Active SQLAlchemy session.
        :param user_id: Identity user id (UUID or string).
        :param reason: Why the sessions were closed, recorded on each
                       event (e.g. ``"user_deactivated"``).
        :param actor_user_id: Who caused the close (an administrator),
                              recorded on each event so the audit log
                              attributes it; None for the owner.
        :param keep_session_id: A session to leave open (the caller's
                                own, e.g. after a password change).

        :returns: Number of sessions closed.
    """
    sessions = (
        db_session.query(AuthSession)
        .filter(AuthSession.user_id == user_id)
        .all()
    )
    if keep_session_id is not None:
        sessions = [
            session for session in sessions
            if str(session.session_id) != str(keep_session_id)
        ]
    closed_at = utc_now().isoformat()
    for session in sessions:
        payload = {
            "session_id": str(session.session_id),
            "user_id": str(session.user_id),
            "reason": reason,
            "actor_user_id": actor_user_id,
            "closed_at": closed_at,
        }
        event = EntityEvent(
            topic=AuthEventTopics.SESSION_CLOSED,
            payload=payload,
            source_event_id=new_uuid(),
        )
        db_session.delete(session)
        enqueue_event(db_session=db_session, event=event)

    rtnval = len(sessions)
    return rtnval


def close_session(
        *,
        db_session: DbSession,
        session_id: str,
        reason: str = "user_logout",
        actor_user_id: Optional[str] = None
    ) -> None:
    """
        Close a session and publish ``entity.session.closed``.

        :param db_session: Active SQLAlchemy session.
        :param session_id: Session id to close.
        :param reason: Why the session ended (``"user_logout"`` for a
                       sign-out, ``"admin_terminated"`` when an
                       administrator ends someone's session).
        :param actor_user_id: Who ended it when that is not the
                              session's owner; recorded so the audit log
                              attributes the termination.

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
        "reason": reason,
        "actor_user_id": actor_user_id,
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
