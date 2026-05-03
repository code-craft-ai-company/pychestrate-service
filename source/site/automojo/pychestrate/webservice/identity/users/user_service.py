"""
.. module:: identity.users.user_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for the 1-user-management feature.

.. moduleauthor:: Automation Mojo LLC

Implements the M1 skeleton of ``create_user`` / ``read_user`` per the
``1-user-management`` spec. Every mutation stages an outbox entry that
the session's after-commit hook publishes onto the in-process bus.
Downstream consumers (``1-audit-log``) register their subscribers against
the topic constants in :mod:`events`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import os
import secrets

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.users.events import UserEventTopics
from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.identity.users.models import (
    IdentityEmailVerification,
    IdentityUser,
    UserStatus,
)
from automojo.pychestrate.webservice.identity.users.repositories import user_repository
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


EMAIL_VERIFICATION_TTL = timedelta(hours=24)


SessionRevocationCallback = Callable[[str], None]
_SESSION_REVOCATION_CALLBACK: Optional[SessionRevocationCallback] = None


def set_session_revocation_callback(
        *, callback: Optional[SessionRevocationCallback]
    ) -> None:
    """
        Register the callback the deactivate path invokes after
        a successful flip to :data:`UserStatus.DEACTIVATED`. The
        callback receives the user id and is expected to revoke
        every active session for that user via
        ``1-authentication``. ``None`` clears the registration —
        used by tests.
    """
    global _SESSION_REVOCATION_CALLBACK
    _SESSION_REVOCATION_CALLBACK = callback
    return


def reset_for_testing() -> None:
    """
        Drop module-level caches; tests use this to keep the
        revocation-callback registration from leaking across
        cases.
    """
    global _SESSION_REVOCATION_CALLBACK
    _SESSION_REVOCATION_CALLBACK = None
    return


@dataclass(frozen=True)
class UserListPage:
    """
        Cursor-paginated user list.

        :param users: Rows on this page in stable
                      ``(created_at, user_id)`` order.
        :param next_cursor: Encoded cursor consumed by the next
                            call; ``None`` when no more rows.
    """
    users: Tuple[IdentityUser, ...]
    next_cursor: Optional[str]


@dataclass(frozen=True)
class EmailVerificationChallenge:
    """
        Payload returned by :func:`request_email_change`. The
        plain-text token is delivered to the user's existing
        primary email; the hash is what the table stores so a
        leaked DB row cannot be replayed against the endpoint.
    """
    verification_id: str
    token: str
    expires_at: datetime


def create_user(
        *,
        db_session: DbSession,
        login_name: str,
        primary_email: str,
        display_name: str,
        timezone: str,
        provisioning_source: str,
        external_id: Optional[str],
        actor_user_id: Optional[str]
    ) -> IdentityUser:
    """
        Create a new identity user record.

        :param db_session: Active SQLAlchemy session.
        :param login_name: Unique account login; normalized to lower case.
        :param primary_email: RFC-5321 email address; normalized to lower case.
        :param display_name: Human-facing name.
        :param timezone: IANA timezone name.
        :param provisioning_source: Source name; ``"local"`` for admin-created.
        :param external_id: Stable id from the external source, if any.
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The newly created :class:`IdentityUser`.
        :raises: UserAlreadyExistsError, SemanticError
    """
    if login_name is None or len(login_name.strip()) == 0:
        raise SemanticError("create_user requires a non-empty login_name")

    if primary_email is None or len(primary_email.strip()) == 0:
        raise SemanticError("create_user requires a non-empty primary_email")

    normalized_login = login_name.strip().lower()
    normalized_email = primary_email.strip().lower()

    existing_login = user_repository.get_by_login_name(
        db_session=db_session, login_name=normalized_login
    )
    if existing_login is not None:
        _raise_already_exists(login_name=normalized_login, conflict_field="login_name")

    existing_email = user_repository.get_by_email(
        db_session=db_session, primary_email=normalized_email
    )
    if existing_email is not None:
        _raise_already_exists(login_name=normalized_login, conflict_field="primary_email")

    now = utc_now()
    user = IdentityUser(
        user_id=new_uuid(),
        login_name=normalized_login,
        primary_email=normalized_email,
        display_name=display_name,
        status=UserStatus.ACTIVE,
        provisioning_source=provisioning_source,
        external_id=external_id,
        timezone=timezone,
        created_at=now,
        updated_at=now,
    )

    try:
        user_repository.insert(db_session=db_session, user=user)
    except IntegrityError as xcpt:
        _raise_already_exists(
            login_name=normalized_login, conflict_field="login_name_or_email"
        )

    event_payload = {
        "user_id": user.user_id,
        "login_name": user.login_name,
        "provisioning_source": user.provisioning_source,
        "actor_user_id": actor_user_id,
        "created_at": user.created_at.isoformat(),
    }
    event = EntityEvent(
        topic=UserEventTopics.USER_CREATED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = user
    return rtnval


def read_user(*, db_session: DbSession, user_id: str) -> IdentityUser:
    """
        Return the identity user with the given id.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Target user id.

        :returns: The :class:`IdentityUser`.
        :raises: UserNotFoundError
    """
    user = user_repository.get_by_id(db_session=db_session, user_id=user_id)
    if user is None:
        err_msg_lines = ["Cannot read user — record not found."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise UserNotFoundError(err_msg) from None

    rtnval = user
    return rtnval


def _raise_already_exists(*, login_name: str, conflict_field: str) -> None:
    """
        Construct and raise a multi-line UserAlreadyExistsError.

        :param login_name: The login that collided.
        :param conflict_field: Which unique column reported the conflict.

        :returns: None — never returns.
        :raises: UserAlreadyExistsError
    """
    err_msg_lines = ["Cannot create user — conflict with existing record."]
    err_msg_lines.append("LOGIN_NAME: {}".format(login_name))
    err_msg_lines.append("CONFLICT_FIELD: {}".format(conflict_field))
    err_msg = os.linesep.join(err_msg_lines)
    raise UserAlreadyExistsError(err_msg) from None


def deactivate_user(
        *,
        db_session: DbSession,
        user_id: str,
        reason: str = "",
        actor_user_id: Optional[str] = None
    ) -> IdentityUser:
    """
        Flip ``user_id``'s status to ``DEACTIVATED``, drop any
        pending email-verification rows, invoke the registered
        session-revocation callback, and emit
        :data:`UserEventTopics.USER_DEACTIVATED`. Idempotent on
        already-deactivated users.

        :raises: UserNotFoundError on miss.
    """
    user = read_user(db_session=db_session, user_id=user_id)
    if user.status == UserStatus.DEACTIVATED:
        rtnval = user
        return rtnval

    now = utc_now()
    user_repository.update_status(
        db_session=db_session,
        user_id=user_id,
        status=UserStatus.DEACTIVATED,
        updated_at=now,
    )
    user_repository.delete_email_verifications_for_user(
        db_session=db_session, user_id=user_id,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.USER_DEACTIVATED,
            payload={
                "user_id": user_id,
                "reason": reason,
                "actor_user_id": actor_user_id,
                "deactivated_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    if _SESSION_REVOCATION_CALLBACK is not None:
        _SESSION_REVOCATION_CALLBACK(user_id)

    rtnval = read_user(db_session=db_session, user_id=user_id)
    return rtnval


def reactivate_user(
        *,
        db_session: DbSession,
        user_id: str,
        actor_user_id: Optional[str] = None
    ) -> IdentityUser:
    """
        Flip ``user_id``'s status from ``DEACTIVATED`` back to
        ``ACTIVE`` and emit
        :data:`UserEventTopics.USER_REACTIVATED`. Idempotent on
        already-active users (returns the row without emitting).

        :raises: UserNotFoundError on miss; SemanticError when
                 reactivating a user whose status is neither
                 ACTIVE nor DEACTIVATED (e.g. PENDING).
    """
    user = read_user(db_session=db_session, user_id=user_id)
    if user.status == UserStatus.ACTIVE:
        rtnval = user
        return rtnval
    if user.status != UserStatus.DEACTIVATED:
        err_lines = ["reactivate_user requires a DEACTIVATED source row."]
        err_lines.append("USER_ID: {}".format(user_id))
        err_lines.append("STATUS: {}".format(user.status.value))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    now = utc_now()
    user_repository.update_status(
        db_session=db_session,
        user_id=user_id,
        status=UserStatus.ACTIVE,
        updated_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.USER_REACTIVATED,
            payload={
                "user_id": user_id,
                "actor_user_id": actor_user_id,
                "reactivated_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = read_user(db_session=db_session, user_id=user_id)
    return rtnval


def list_users(
        *,
        db_session: DbSession,
        status: Optional[UserStatus] = None,
        provisioning_source: Optional[str] = None,
        login_prefix: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50
    ) -> UserListPage:
    """
        Cursor-paginated user list with optional filters.

        :param db_session: Active SQLAlchemy session.
        :param status: Optional :class:`UserStatus` filter.
        :param provisioning_source: Optional source filter.
        :param login_prefix: Case-insensitive ``login_name``
                             prefix filter.
        :param cursor: Opaque cursor returned by a prior call;
                       ``None`` for the first page.
        :param limit: Max rows per page (capped at 200).

        :returns: :class:`UserListPage`.
    """
    if limit <= 0:
        err_lines = ["list_users requires a positive limit."]
        err_lines.append("VALUE: {}".format(limit))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    materialized_limit = min(limit, 200)
    decoded_cursor = _decode_cursor(cursor=cursor)
    rows = user_repository.list_with_filters(
        db_session=db_session,
        status=status,
        provisioning_source=provisioning_source,
        login_prefix=login_prefix,
        cursor=decoded_cursor,
        limit=materialized_limit + 1,
    )
    if len(rows) > materialized_limit:
        page_rows = rows[:materialized_limit]
        last = page_rows[-1]
        next_cursor = _encode_cursor(
            created_at=last.created_at, user_id=str(last.user_id),
        )
    else:
        page_rows = rows
        next_cursor = None
    rtnval = UserListPage(
        users=tuple(page_rows), next_cursor=next_cursor,
    )
    return rtnval


def request_email_change(
        *,
        db_session: DbSession,
        user_id: str,
        new_email: str,
        actor_user_id: Optional[str] = None
    ) -> EmailVerificationChallenge:
    """
        Issue a 24-hour email-change verification token. Caller
        delivers the plain-text ``token`` to the *current*
        primary email; only the hash lands in the table.

        :raises: UserNotFoundError on miss; SemanticError on
                 empty / malformed input or when the user is
                 not ACTIVE; UserAlreadyExistsError when the
                 new email is already in use by another user.
    """
    if new_email is None or len(new_email.strip()) == 0:
        err_lines = ["request_email_change requires a non-empty new_email."]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    user = read_user(db_session=db_session, user_id=user_id)
    if user.status != UserStatus.ACTIVE:
        err_lines = [
            "request_email_change requires an ACTIVE source row.",
        ]
        err_lines.append("USER_ID: {}".format(user_id))
        err_lines.append("STATUS: {}".format(user.status.value))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    normalized_email = new_email.strip().lower()
    if normalized_email == user.primary_email:
        err_lines = [
            "request_email_change requires a different new_email.",
        ]
        err_lines.append("USER_ID: {}".format(user_id))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    collision = user_repository.get_by_email(
        db_session=db_session, primary_email=normalized_email,
    )
    if collision is not None and str(collision.user_id) != str(user_id):
        _raise_already_exists(
            login_name=user.login_name,
            conflict_field="primary_email",
        )

    # Drop any prior pending verifications for this user so the
    # most recently issued token is the only valid challenge.
    user_repository.delete_email_verifications_for_user(
        db_session=db_session, user_id=user_id,
    )

    now = utc_now()
    expires_at = now + EMAIL_VERIFICATION_TTL
    token_bytes = secrets.token_bytes(32)
    token_str = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    token_hash = hashlib.sha256(token_str.encode("ascii")).digest()
    verification = IdentityEmailVerification(
        verification_id=new_uuid(),
        user_id=user_id,
        new_email=normalized_email,
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
    )
    user_repository.insert_email_verification(
        db_session=db_session, verification=verification,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.USER_UPDATED,
            payload={
                "user_id": user_id,
                "field": "primary_email",
                "phase": "verification_requested",
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = EmailVerificationChallenge(
        verification_id=str(verification.verification_id),
        token=token_str,
        expires_at=expires_at,
    )
    return rtnval


def confirm_email_change(
        *,
        db_session: DbSession,
        token: str,
        actor_user_id: Optional[str] = None
    ) -> IdentityUser:
    """
        Verify an email-change token, swap the user's
        ``primary_email``, and emit
        :data:`UserEventTopics.USER_UPDATED`.

        :raises: SemanticError on empty / unknown / expired
                 token; UserNotFoundError when the row vanished
                 between request and confirm.
    """
    if token is None or len(token) == 0:
        err_lines = ["confirm_email_change requires a non-empty token."]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    token_hash = hashlib.sha256(token.encode("ascii")).digest()
    row = user_repository.find_email_verification_by_token(
        db_session=db_session, token_hash=token_hash,
    )
    if row is None:
        err_lines = ["Email verification token not recognized."]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    expires = _aware(value=row.expires_at)
    now = utc_now()
    if now > expires:
        # Surface a fresh row read so the caller sees the cleanup.
        user_repository.delete_email_verifications_for_user(
            db_session=db_session, user_id=str(row.user_id),
        )
        db_session.commit()
        err_lines = ["Email verification token has expired."]
        err_lines.append("EXPIRES_AT: {}".format(expires.isoformat()))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    user_repository.update_email(
        db_session=db_session,
        user_id=str(row.user_id),
        new_email=row.new_email,
        updated_at=now,
    )
    user_repository.delete_email_verifications_for_user(
        db_session=db_session, user_id=str(row.user_id),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.USER_UPDATED,
            payload={
                "user_id": str(row.user_id),
                "field": "primary_email",
                "phase": "verified",
                "actor_user_id": actor_user_id,
                "new_email": row.new_email,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = read_user(db_session=db_session, user_id=str(row.user_id))
    return rtnval


def update_profile(
        *,
        db_session: DbSession,
        user_id: str,
        display_name: Optional[str] = None,
        timezone_name: Optional[str] = None,
        actor_user_id: Optional[str] = None
    ) -> IdentityUser:
    """
        Update non-identifier profile fields (``display_name``,
        ``timezone``). At least one of ``display_name`` /
        ``timezone_name`` must be supplied. Email changes go
        through :func:`request_email_change`.
    """
    if display_name is None and timezone_name is None:
        err_lines = [
            "update_profile requires at least one mutating field.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    user = read_user(db_session=db_session, user_id=user_id)
    if display_name is not None:
        user.display_name = display_name
    if timezone_name is not None:
        user.timezone = timezone_name
    user.updated_at = utc_now()
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.USER_UPDATED,
            payload={
                "user_id": user_id,
                "field": "profile",
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = read_user(db_session=db_session, user_id=user_id)
    return rtnval


def _encode_cursor(*, created_at: datetime, user_id: str) -> str:
    """
        Encode an exclusive ``(created_at, user_id)`` cursor
        as a URL-safe string. The format is
        ``base64url("<iso8601>.<uuid>")``; the embedded dot is
        the separator.
    """
    aware = _aware(value=created_at)
    raw = "{}.{}".format(aware.isoformat(), user_id)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    rtnval = encoded.rstrip("=")
    return rtnval


def _decode_cursor(*, cursor: Optional[str]):
    """
        Decode an opaque cursor into ``(created_at, user_id)``;
        returns ``None`` for an empty / unset cursor. Raises
        ValueError on malformed values.
    """
    if cursor is None or len(cursor) == 0:
        return None
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
    except Exception as decode_err:
        err_lines = ["Cursor is not a valid base64url string."]
        err_lines.append("DETAIL: {}".format(decode_err))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    parts = raw.rsplit(".", 1)
    if len(parts) != 2:
        err_lines = ["Cursor payload is malformed."]
        err_lines.append("VALUE: {!r}".format(raw))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    iso, user_id = parts
    try:
        created_at = datetime.fromisoformat(iso)
    except ValueError as ts_err:
        err_lines = ["Cursor timestamp is not ISO-8601."]
        err_lines.append("VALUE: {!r}".format(iso))
        err_lines.append("DETAIL: {}".format(ts_err))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    return (created_at, user_id)


def _aware(*, value: datetime) -> datetime:
    """
        Normalize a SQLAlchemy-returned datetime to UTC-aware.
        SQLite drops tz info; Postgres preserves it. Both must
        round-trip cleanly through cursor compares and TTL
        checks.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
