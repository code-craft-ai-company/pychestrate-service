"""
.. module:: security.auth.password_lifecycle
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Setting, resetting and changing local passwords, and the
               single-use invite / reset links (audit ADM-04).

.. moduleauthor:: Code Craft AI LLC

Before this module a local account had no password lifecycle: an
administrator could not set a new password for a user who forgot
theirs, a user could never change the password they were given, and
there were no invite or reset links. The pieces:

* :func:`admin_set_password` -- an administrator sets a new
  (temporary) password, by default one the user must replace at their
  next sign-in (``AuthLocalCredentials.must_rotate_after``).
* :func:`issue_password_link` -- an administrator creates a
  single-use link (an *invite* for an account that has no password
  yet, a *reset* otherwise) and hands it to the user; the product
  sends no email yet. Only the SHA-256 digest of the link secret is
  stored; links expire (:data:`INVITE_LINK_TTL`,
  :data:`RESET_LINK_TTL`) and issuing a new one revokes the old ones.
* :func:`redeem_password_link` -- the user opens the link and chooses
  a password; an invited account becomes active.
* :func:`change_own_password` -- a signed-in user (or one whose
  password must be replaced before they can sign in) changes their
  password after proving the current one.

Every path enforces :mod:`security.auth.password_policy`, closes the
account's other sessions when its password changes, and publishes an
``entity.user.password_*`` event the audit log records. Callers own
the transaction: functions flush, the caller commits (the events are
published on commit).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import secrets
import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ccai.pychestrate.webservice.security.auth.password_policy import (
    PasswordPolicyError,
    enforce_password_policy,
)


INVITE_LINK_TTL: timedelta = timedelta(days=7)
RESET_LINK_TTL: timedelta = timedelta(hours=24)

#: Bytes of randomness in a link secret (256 bits).
_LINK_SECRET_BYTES: int = 32

TOPIC_PASSWORD_CHANGED: str = "entity.user.password_changed"
TOPIC_PASSWORD_RESET: str = "entity.user.password_reset"
TOPIC_PASSWORD_LINK_ISSUED: str = "entity.user.password_link_issued"
TOPIC_PASSWORD_LINK_REDEEMED: str = "entity.user.password_link_redeemed"

SESSION_CLOSE_REASON_RESET: str = "password_reset"
SESSION_CLOSE_REASON_CHANGED: str = "password_changed"


class PasswordLifecycleError(Exception):
    """
        A password operation was refused. ``message`` is safe to show.
    """

    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)
        return


class PasswordLinkInvalidError(PasswordLifecycleError):
    """
        The link is unknown, used, revoked, expired, or its account can
        no longer sign in. One message for every case, so a link's
        state is not revealed to whoever holds it.
    """

    def __init__(self) -> None:
        super().__init__(
            "This link is not valid. It may have expired or already been "
            "used. Ask an administrator for a new one."
        )
        return


class CurrentPasswordMismatchError(PasswordLifecycleError):
    """
        The current password given to confirm a change is wrong.
    """

    def __init__(self) -> None:
        super().__init__("The current password is not correct.")
        return


@dataclass(frozen=True)
class IssuedPasswordLink:
    """
        A freshly issued link. ``secret`` is shown once and never
        stored.

        :param token_id: The token row id.
        :param user_id: The account the link is for.
        :param purpose: ``"INVITE"`` or ``"RESET"``.
        :param secret: The link secret (goes into the URL).
        :param expires_at: When the link stops working.
    """
    token_id: str
    user_id: str
    purpose: str
    secret: str
    expires_at: datetime


@dataclass(frozen=True)
class RedeemedPasswordLink:
    """
        The outcome of a redeemed link.

        :param user_id: The account whose password was set.
        :param login_name: Its login name.
        :param purpose: ``"INVITE"`` or ``"RESET"``.
    """
    user_id: str
    login_name: str
    purpose: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    rtnval = datetime.now(timezone.utc)
    return rtnval


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
        Treat a naive datetime (SQLite) as UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    return value


def hash_link_secret(*, secret: str) -> str:
    """
        The stored digest of a link secret.

        :param secret: The secret from the link.

        :returns: Lower-case SHA-256 hex digest.
    """
    rtnval = hashlib.sha256(str(secret).encode("utf-8")).hexdigest()
    return rtnval


def _parse_uuid(*, value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        rtnval = uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
    return rtnval


def _load_user(*, db_session: Any, user_id: Any) -> Any:
    """
        The identity user, or a :class:`PasswordLifecycleError`.
    """
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402

    user_uuid = _parse_uuid(value=user_id)
    row = None
    if user_uuid is not None:
        row = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.user_id == user_uuid)
            .first()
        )
    if row is None:
        raise PasswordLifecycleError("User not found.")
    return row


def _publish(*, db_session: Any, topic: str, payload: Dict[str, Any]) -> None:
    """
        Stage an entity event on the session's outbox (published, and
        audited, when the caller commits).
    """
    from ccai.pychestrate.core.defaults import new_uuid  # noqa: E402
    from ccai.pychestrate.webservice.audit.data_change_bridge import (  # noqa: E402
        session_client_address,
    )
    from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent  # noqa: E402
    from ccai.pychestrate.webservice.messaging.outbox import enqueue_event  # noqa: E402

    full_payload = dict(payload)
    if "client_address" not in full_payload:
        full_payload["client_address"] = session_client_address(db_session=db_session)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(topic=topic, payload=full_payload, source_event_id=new_uuid()),
    )
    return


def _revoke_open_links(*, db_session: Any, user_uuid: Any, now: datetime) -> int:
    """
        Revoke every unused, unrevoked link of an account.

        :returns: Number of links revoked.
    """
    from ccai.pychestrate.webservice.security.auth.models import AuthPasswordToken  # noqa: E402

    rows = (
        db_session.query(AuthPasswordToken)
        .filter(AuthPasswordToken.user_id == user_uuid)
        .filter(AuthPasswordToken.used_at.is_(None))
        .filter(AuthPasswordToken.revoked_at.is_(None))
        .all()
    )
    for row in rows:
        row.revoked_at = now
    db_session.flush()
    rtnval = len(rows)
    return rtnval


def _store_password(
        *,
        db_session: Any,
        user_uuid: Any,
        password: str,
        must_change: bool,
        now: datetime
    ) -> None:
    """
        Hash and store a password (creating the credentials row for an
        account that has none, e.g. an invited one).
    """
    from ccai.pychestrate.webservice.security.auth import local_flow  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials,
    )

    encoded_hash, algo_params = local_flow.hash_password(password=password)
    credentials = (
        db_session.query(AuthLocalCredentials)
        .filter(AuthLocalCredentials.user_id == user_uuid)
        .first()
    )
    if credentials is None:
        credentials = AuthLocalCredentials(
            user_id=user_uuid,
            argon2id_hash=encoded_hash,
            algo_params=algo_params,
        )
        db_session.add(credentials)
    else:
        credentials.argon2id_hash = encoded_hash
        credentials.algo_params = algo_params
    credentials.last_changed_at = now
    credentials.must_rotate_after = now if must_change is True else None
    db_session.flush()
    return


def _close_sessions(
        *,
        db_session: Any,
        user_uuid: Any,
        reason: str,
        actor_user_id: Optional[str],
        keep_session_id: Optional[str] = None
    ) -> None:
    from ccai.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
        close_sessions_for_user,
    )
    close_sessions_for_user(
        db_session=db_session,
        user_id=user_uuid,
        reason=reason,
        actor_user_id=actor_user_id,
        keep_session_id=keep_session_id,
    )
    return


def password_change_required(*, db_session: Any, user_id: Any, now: Optional[datetime] = None) -> bool:
    """
        Whether the account must replace its password before it may
        sign in (an administrator set a temporary one).

        :param db_session: Active SQLAlchemy session.
        :param user_id: The account.
        :param now: Evaluation time (defaults to now).

        :returns: True when ``must_rotate_after`` has passed.
    """
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials,
    )

    user_uuid = _parse_uuid(value=user_id)
    if user_uuid is None:
        return False
    credentials = (
        db_session.query(AuthLocalCredentials)
        .filter(AuthLocalCredentials.user_id == user_uuid)
        .first()
    )
    if credentials is None:
        return False
    deadline = _as_utc(credentials.must_rotate_after)
    if deadline is None:
        return False
    reference = now if now is not None else _now()
    rtnval = deadline <= reference
    return rtnval


def verify_current_password(*, db_session: Any, user_id: Any, password: str) -> bool:
    """
        Whether ``password`` is the account's current password.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The account.
        :param password: Candidate password.

        :returns: True on a match.
    """
    from ccai.pychestrate.webservice.security.auth import local_flow  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials,
    )

    user_uuid = _parse_uuid(value=user_id)
    if user_uuid is None or password is None or len(password) == 0:
        return False
    credentials = (
        db_session.query(AuthLocalCredentials)
        .filter(AuthLocalCredentials.user_id == user_uuid)
        .first()
    )
    if credentials is None:
        return False
    rtnval = local_flow._verify_stored_hash(
        stored_hash=bytes(credentials.argon2id_hash),
        algo_params=credentials.algo_params or {},
        password=password,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def issue_password_link(
        *,
        db_session: Any,
        user_id: Any,
        purpose: str,
        actor_user_id: Optional[str],
        now: Optional[datetime] = None
    ) -> IssuedPasswordLink:
    """
        Create a single-use link for ``user_id`` and revoke the
        account's older links. Refused for a deactivated account.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The account.
        :param purpose: ``"INVITE"`` or ``"RESET"``.
        :param actor_user_id: The administrator issuing it.
        :param now: Evaluation time (defaults to now).

        :returns: :class:`IssuedPasswordLink` (the secret is shown once).
        :raises: PasswordLifecycleError
    """
    from ccai.pychestrate.webservice.identity.users.models import UserStatus  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthPasswordToken,
        PasswordTokenPurpose,
    )

    reference = now if now is not None else _now()
    user = _load_user(db_session=db_session, user_id=user_id)
    if user.status == UserStatus.DEACTIVATED:
        raise PasswordLifecycleError(
            "This account is deactivated. Reactivate it before creating a link."
        )
    token_purpose = PasswordTokenPurpose(purpose)
    ttl = INVITE_LINK_TTL if token_purpose == PasswordTokenPurpose.INVITE else RESET_LINK_TTL

    _revoke_open_links(db_session=db_session, user_uuid=user.user_id, now=reference)

    secret = secrets.token_urlsafe(_LINK_SECRET_BYTES)
    token_id = uuid.uuid4()
    expires_at = reference + ttl
    db_session.add(AuthPasswordToken(
        token_id=token_id,
        user_id=user.user_id,
        purpose=token_purpose,
        token_hash=hash_link_secret(secret=secret),
        created_at=reference,
        created_by=_parse_uuid(value=actor_user_id),
        expires_at=expires_at,
        used_at=None,
        revoked_at=None,
    ))
    db_session.flush()

    _publish(db_session=db_session, topic=TOPIC_PASSWORD_LINK_ISSUED, payload={
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "purpose": token_purpose.value.lower(),
        "expires_at": expires_at.isoformat(),
        "actor_user_id": actor_user_id,
    })

    rtnval = IssuedPasswordLink(
        token_id=str(token_id),
        user_id=str(user.user_id),
        purpose=token_purpose.value,
        secret=secret,
        expires_at=expires_at,
    )
    return rtnval


def find_usable_link(*, db_session: Any, secret: str, now: Optional[datetime] = None) -> Any:
    """
        The token row a link secret names, when it is still usable and
        its account can use it (not deactivated). Raises
        :class:`PasswordLinkInvalidError` otherwise.

        :param db_session: Active SQLAlchemy session.
        :param secret: The secret from the link.
        :param now: Evaluation time (defaults to now).

        :returns: ``(token_row, user_row)``.
        :raises: PasswordLinkInvalidError
    """
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
        UserStatus,
    )
    from ccai.pychestrate.webservice.security.auth.models import AuthPasswordToken  # noqa: E402

    reference = now if now is not None else _now()
    if secret is None or len(str(secret).strip()) == 0 or len(str(secret)) > 256:
        raise PasswordLinkInvalidError()
    token = (
        db_session.query(AuthPasswordToken)
        .filter(AuthPasswordToken.token_hash == hash_link_secret(secret=str(secret).strip()))
        .first()
    )
    if token is None or token.used_at is not None or token.revoked_at is not None:
        raise PasswordLinkInvalidError()
    expires_at = _as_utc(token.expires_at)
    if expires_at is None or expires_at <= reference:
        raise PasswordLinkInvalidError()
    user = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == token.user_id)
        .first()
    )
    if user is None or user.status == UserStatus.DEACTIVATED:
        raise PasswordLinkInvalidError()
    rtnval = (token, user)
    return rtnval


def redeem_password_link(
        *,
        db_session: Any,
        secret: str,
        new_password: str,
        now: Optional[datetime] = None
    ) -> RedeemedPasswordLink:
    """
        Set the account's password from a link and use the link up. An
        invited account becomes active; the account's sessions are
        closed.

        :param db_session: Active SQLAlchemy session.
        :param secret: The secret from the link.
        :param new_password: The password the user chose.
        :param now: Evaluation time (defaults to now).

        :returns: :class:`RedeemedPasswordLink`.
        :raises: PasswordLinkInvalidError, PasswordPolicyError
    """
    from ccai.pychestrate.webservice.identity.users.models import UserStatus  # noqa: E402

    reference = now if now is not None else _now()
    token, user = find_usable_link(db_session=db_session, secret=secret, now=reference)
    enforce_password_policy(
        password=new_password, login_name=user.login_name, email=user.primary_email
    )

    _store_password(
        db_session=db_session,
        user_uuid=user.user_id,
        password=new_password,
        must_change=False,
        now=reference,
    )
    token.used_at = reference
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    user.updated_at = reference
    _revoke_open_links(db_session=db_session, user_uuid=user.user_id, now=reference)
    _close_sessions(
        db_session=db_session,
        user_uuid=user.user_id,
        reason=SESSION_CLOSE_REASON_RESET,
        actor_user_id=str(user.user_id),
    )
    db_session.flush()

    _publish(db_session=db_session, topic=TOPIC_PASSWORD_LINK_REDEEMED, payload={
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "purpose": token.purpose.value.lower(),
        "actor_user_id": str(user.user_id),
    })

    rtnval = RedeemedPasswordLink(
        user_id=str(user.user_id),
        login_name=user.login_name,
        purpose=token.purpose.value,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Admin set / self-service change
# ---------------------------------------------------------------------------


def admin_set_password(
        *,
        db_session: Any,
        user_id: Any,
        new_password: str,
        must_change: bool,
        actor_user_id: Optional[str],
        now: Optional[datetime] = None
    ) -> None:
    """
        An administrator sets a user's password (typically a temporary
        one the user must replace at next sign-in). The user's sessions
        are closed and outstanding links revoked; an invited account
        becomes active.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The account.
        :param new_password: The new password.
        :param must_change: Require a new password at next sign-in.
        :param actor_user_id: The administrator.
        :param now: Evaluation time (defaults to now).

        :returns: None.
        :raises: PasswordLifecycleError, PasswordPolicyError
    """
    from ccai.pychestrate.webservice.identity.users.models import UserStatus  # noqa: E402

    reference = now if now is not None else _now()
    user = _load_user(db_session=db_session, user_id=user_id)
    if actor_user_id is not None and str(actor_user_id) == str(user.user_id):
        raise PasswordLifecycleError(
            "To change your own password, use Change password on your "
            "Preferences page; it asks for your current password."
        )
    if user.status == UserStatus.DEACTIVATED:
        raise PasswordLifecycleError(
            "This account is deactivated. Reactivate it before setting a password."
        )
    enforce_password_policy(
        password=new_password, login_name=user.login_name, email=user.primary_email
    )

    _store_password(
        db_session=db_session,
        user_uuid=user.user_id,
        password=new_password,
        must_change=must_change,
        now=reference,
    )
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    user.updated_at = reference
    _revoke_open_links(db_session=db_session, user_uuid=user.user_id, now=reference)
    _close_sessions(
        db_session=db_session,
        user_uuid=user.user_id,
        reason=SESSION_CLOSE_REASON_RESET,
        actor_user_id=actor_user_id,
    )
    db_session.flush()

    _publish(db_session=db_session, topic=TOPIC_PASSWORD_RESET, payload={
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "must_change": bool(must_change),
        "actor_user_id": actor_user_id,
    })
    return


def change_own_password(
        *,
        db_session: Any,
        user_id: Any,
        current_password: str,
        new_password: str,
        keep_session_id: Optional[str],
        forced: bool = False,
        source_ip: str = "",
        now: Optional[datetime] = None
    ) -> None:
    """
        A user replaces their own password after proving the current
        one. Their other sessions are closed (``keep_session_id`` stays
        open) and a pending "must change" requirement is cleared. The
        current password is checked through ``local_flow`` so repeated
        wrong guesses hit the same back-off as the sign-in form.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The account.
        :param current_password: The password being replaced.
        :param new_password: The new password.
        :param keep_session_id: The session making the change, kept.
        :param forced: The change was required at sign-in.
        :param source_ip: Client address, for the back-off key.
        :param now: Evaluation time (defaults to now).

        :returns: None.
        :raises: CurrentPasswordMismatchError, PasswordLifecycleError,
                 PasswordPolicyError
    """
    from ccai.pychestrate.webservice.identity.users.models import UserStatus  # noqa: E402
    from ccai.pychestrate.webservice.security.auth import local_flow  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.exceptions import (  # noqa: E402
        AuthenticationError,
    )

    reference = now if now is not None else _now()
    user = _load_user(db_session=db_session, user_id=user_id)
    if user.status != UserStatus.ACTIVE:
        raise PasswordLifecycleError("This account is not active.")
    try:
        local_flow.verify_local_credentials(
            login_name=user.login_name,
            password=current_password,
            mfa_code=None,
            source_ip=source_ip if source_ip is not None else "",
            db_session=db_session,
        )
    except AuthenticationError as exc:
        if str(exc).startswith("Too many") is True:
            raise PasswordLifecycleError(
                "Too many recent failures; try again later."
            ) from None
        raise CurrentPasswordMismatchError() from None
    if new_password == current_password:
        raise PasswordPolicyError(
            ["The new password must be different from the current one."]
        )
    enforce_password_policy(
        password=new_password, login_name=user.login_name, email=user.primary_email
    )

    _store_password(
        db_session=db_session,
        user_uuid=user.user_id,
        password=new_password,
        must_change=False,
        now=reference,
    )
    user.updated_at = reference
    _revoke_open_links(db_session=db_session, user_uuid=user.user_id, now=reference)
    _close_sessions(
        db_session=db_session,
        user_uuid=user.user_id,
        reason=SESSION_CLOSE_REASON_CHANGED,
        actor_user_id=str(user.user_id),
        keep_session_id=keep_session_id,
    )
    db_session.flush()

    _publish(db_session=db_session, topic=TOPIC_PASSWORD_CHANGED, payload={
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "forced": bool(forced),
        "actor_user_id": str(user.user_id),
    })
    return


__all__ = [
    "CurrentPasswordMismatchError",
    "INVITE_LINK_TTL",
    "IssuedPasswordLink",
    "PasswordLifecycleError",
    "PasswordLinkInvalidError",
    "RESET_LINK_TTL",
    "RedeemedPasswordLink",
    "admin_set_password",
    "change_own_password",
    "find_usable_link",
    "hash_link_secret",
    "issue_password_link",
    "password_change_required",
    "redeem_password_link",
    "verify_current_password",
]
