"""
.. module:: security.auth.api_tokens.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Issue, list, revoke, and authenticate API tokens; create
               and list service accounts.

.. moduleauthor:: Code Craft AI LLC

Machine callers (the ``pyc`` CLI, CI jobs, MCP agents) authenticate
with an API token sent as ``Authorization: Bearer <token>``. Two kinds
of principal hold tokens:

* **People** -- a personal access token acts as the user who created
  it, with exactly that user's RBAC.
* **Service accounts** -- identity users whose
  ``provisioning_source`` is :data:`SERVICE_ACCOUNT_PROVISIONING_SOURCE`.
  They have no password (the sign-in form cannot open a session for
  them), receive roles through the normal Users / Roles pages, and
  get tokens from an administrator.

Rules every token follows:

* The secret is shown once, when it is issued. Only its SHA-256
  digest is stored.
* Every token expires (:data:`MAX_TOKEN_LIFETIME_DAYS` at most).
* A token never grants more than its principal holds: it carries no
  permissions of its own, and a ``read-only`` token additionally
  refuses every request that is not a safe (read) method.
* A token stops working the moment it is revoked, expires, or its
  account stops being active.
* Creation and revocation are recorded in the audit store; use is
  recorded on the first request and then on the first request of
  each :data:`USE_AUDIT_INTERVAL_SECONDS` window (clock hour, UTC) per
  token, so a busy CI token adds at most one audit record an hour
  (``last_used_at`` keeps the precise last-use time).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import os
import re
import secrets

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.security.auth.api_tokens.events import ApiTokenEventTopics
from ccai.pychestrate.webservice.security.auth.api_tokens.exceptions import (
    ApiTokenNotFoundError,
    ApiTokenRejectedError,
    ApiTokenValidationError,
    ServiceAccountNotFoundError,
)
from ccai.pychestrate.webservice.security.auth.api_tokens.models import AuthApiToken
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal


#: Every token starts with this prefix, so the session middleware can
#: tell an API token from any other bearer value and secret scanners
#: can recognise a leaked one.
TOKEN_PREFIX: str = "pyc_"

#: Bytes of randomness in a token secret (256 bits).
TOKEN_SECRET_BYTES: int = 32

#: Characters of the secret kept (after the prefix) as a display hint.
TOKEN_HINT_LENGTH: int = 6

SCOPE_READ_WRITE: str = "read-write"
SCOPE_READ_ONLY: str = "read-only"
SUPPORTED_SCOPES = (SCOPE_READ_WRITE, SCOPE_READ_ONLY)

#: Methods a ``read-only`` token may use.
SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")

DEFAULT_TOKEN_LIFETIME_DAYS: int = 90
MAX_TOKEN_LIFETIME_DAYS: int = 366
MAX_TOKEN_NAME_LENGTH: int = 128

#: ``last_used_at`` is written at most this often per token, so a CI
#: job making hundreds of calls does not turn every read into a write.
LAST_USED_WRITE_INTERVAL_SECONDS: int = 60

#: A use is recorded in the audit store on a token's first request
#: and then at most once per this interval.
USE_AUDIT_INTERVAL_SECONDS: int = 3600

#: ``IdentityUser.provisioning_source`` value marking a service account.
SERVICE_ACCOUNT_PROVISIONING_SOURCE: str = "service_account"

#: Service accounts have no mailbox; their required ``primary_email``
#: is synthesised under the reserved ``.invalid`` TLD (RFC 2606) so no
#: mail can ever be delivered to it.
SERVICE_ACCOUNT_EMAIL_DOMAIN: str = "service-accounts.invalid"

#: ``provider_name`` carried by principals authenticated with a token.
API_TOKEN_PROVIDER_NAME: str = "api-token"

#: ``session_id`` prefix of token principals (they have no session row).
API_TOKEN_SESSION_ID_PREFIX: str = "api-token:"

TOKEN_STATUS_ACTIVE: str = "active"
TOKEN_STATUS_EXPIRED: str = "expired"
TOKEN_STATUS_REVOKED: str = "revoked"

_SERVICE_ACCOUNT_LOGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")


@dataclass(frozen=True)
class ApiTokenPrincipal(AuthPrincipal):
    """
        The principal of a request authenticated with an API token. It
        is an :class:`AuthPrincipal` for the token's user, so every
        RBAC check sees exactly that user's grants; the extra fields
        let handlers and the middleware tell how the caller signed in.

        :param token_id: The token that authenticated the request.
        :param token_name: Its label.
        :param token_scope: ``read-write`` or ``read-only``.
        :param token_expires_at: Its expiry (UTC).
    """
    token_id: str = ""
    token_name: str = ""
    token_scope: str = SCOPE_READ_WRITE
    token_expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class ApiTokenView:
    """
        Read model for one token. Never carries the secret.

        :param token_id: Token id.
        :param user_id: The user the token acts as.
        :param login_name: That user's login name.
        :param is_service_account: Whether that user is a service
                                   account.
        :param name: Token label.
        :param token_hint: Leading characters, e.g. ``pyc_Ab3xQ9``.
        :param scope: ``read-write`` or ``read-only``.
        :param status: ``active``, ``expired`` or ``revoked``.
        :param created_at: Issue time (UTC).
        :param created_by_user_id: Who issued it.
        :param expires_at: Expiry (UTC).
        :param last_used_at: Last use (UTC) or ``None``.
        :param revoked_at: Revocation time (UTC) or ``None``.
    """
    token_id: str
    user_id: str
    login_name: str
    is_service_account: bool
    name: str
    token_hint: str
    scope: str
    status: str
    created_at: Optional[datetime]
    created_by_user_id: Optional[str]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]

    def to_dict(self) -> Dict[str, Any]:
        """
            Render the view as the REST response body.

            :returns: JSON-friendly dict.
        """
        rtnval = {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "login_name": self.login_name,
            "is_service_account": self.is_service_account,
            "name": self.name,
            "token_hint": self.token_hint,
            "scope": self.scope,
            "status": self.status,
            "created_at": _iso_or_none(self.created_at),
            "created_by_user_id": self.created_by_user_id,
            "expires_at": _iso_or_none(self.expires_at),
            "last_used_at": _iso_or_none(self.last_used_at),
            "revoked_at": _iso_or_none(self.revoked_at),
        }
        return rtnval


@dataclass(frozen=True)
class IssuedApiToken:
    """
        Result of :func:`create_api_token`: the secret (the only time
        it exists outside the caller's hands) plus the stored view.

        :param token: The full token string, ``pyc_...``.
        :param view: The persisted token's read model.
    """
    token: str
    view: ApiTokenView

    def to_dict(self) -> Dict[str, Any]:
        """
            Render the issued token as the REST response body.

            :returns: JSON-friendly dict carrying ``token`` once.
        """
        rtnval = self.view.to_dict()
        rtnval["token"] = self.token
        return rtnval


@dataclass(frozen=True)
class ServiceAccountView:
    """
        Read model for one service account.

        :param user_id: Identity user id.
        :param login_name: Login name.
        :param display_name: Display name.
        :param status: ``ACTIVE`` / ``DEACTIVATED`` / ``PENDING``.
        :param created_at: Creation time (UTC).
        :param active_token_count: Tokens that currently authenticate.
    """
    user_id: str
    login_name: str
    display_name: str
    status: str
    created_at: Optional[datetime]
    active_token_count: int

    def to_dict(self) -> Dict[str, Any]:
        """
            Render the view as the REST response body.

            :returns: JSON-friendly dict.
        """
        rtnval = {
            "user_id": self.user_id,
            "login_name": self.login_name,
            "display_name": self.display_name,
            "status": self.status,
            "created_at": _iso_or_none(self.created_at),
            "active_token_count": self.active_token_count,
        }
        return rtnval


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
        Return ``value`` as a timezone-aware UTC datetime. SQLite hands
        back naive datetimes for ``DateTime(timezone=True)`` columns;
        they were written as UTC.

        :param value: Datetime or ``None``.

        :returns: Aware datetime or ``None``.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    rtnval = value.astimezone(timezone.utc)
    return rtnval


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    """
        ISO-8601 rendering of a UTC datetime, or ``None``.

        :param value: Datetime or ``None``.

        :returns: String or ``None``.
    """
    normalized = _as_utc(value)
    if normalized is None:
        return None
    rtnval = normalized.isoformat()
    return rtnval


def _resolve_now(now: Optional[datetime]) -> datetime:
    """
        Normalize the caller's evaluation time (tests pass a fixed
        clock; production passes ``None``).

        :param now: Optional evaluation time.

        :returns: Aware UTC datetime.
    """
    if now is None:
        rtnval = utc_now()
        return rtnval
    rtnval = _as_utc(now)
    return rtnval


def generate_token_secret() -> str:
    """
        Generate a new token string: :data:`TOKEN_PREFIX` followed by
        :data:`TOKEN_SECRET_BYTES` random bytes, URL-safe base64.

        :returns: Token string.
    """
    rtnval = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_SECRET_BYTES)
    return rtnval


def digest_token(*, token: str) -> str:
    """
        Return the stored digest of a token.

        :param token: Full token string.

        :returns: Lower-case hex SHA-256 digest.
    """
    rtnval = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return rtnval


def looks_like_api_token(*, candidate: Optional[str]) -> bool:
    """
        Whether a bearer value is shaped like one of our tokens. The
        middleware only tries to authenticate values that are, so any
        other bearer credential passes through untouched.

        :param candidate: Raw bearer value.

        :returns: ``True`` for a ``pyc_`` value of plausible length.
    """
    if candidate is None:
        return False
    if candidate.startswith(TOKEN_PREFIX) is False:
        return False
    rtnval = len(TOKEN_PREFIX) < len(candidate) <= 256
    return rtnval


def _token_status(*, row: AuthApiToken, now: datetime) -> str:
    """
        Classify a token row at ``now``.

        :param row: Token row.
        :param now: Evaluation time (aware UTC).

        :returns: One of the ``TOKEN_STATUS_*`` values.
    """
    if row.revoked_at is not None:
        return TOKEN_STATUS_REVOKED
    expires_at = _as_utc(row.expires_at)
    if expires_at is not None and expires_at <= now:
        return TOKEN_STATUS_EXPIRED
    return TOKEN_STATUS_ACTIVE


def is_service_account(*, user: Any) -> bool:
    """
        Whether an identity user is a service account.

        :param user: :class:`IdentityUser` (or any object with
                     ``provisioning_source``).

        :returns: Boolean.
    """
    source = getattr(user, "provisioning_source", None)
    rtnval = source == SERVICE_ACCOUNT_PROVISIONING_SOURCE
    return rtnval


def _load_user(*, db_session: DbSession, user_id: Any) -> Optional[IdentityUser]:
    """
        Load an identity user by id.

        :param db_session: Active SQLAlchemy session.
        :param user_id: User id (UUID or string).

        :returns: The user or ``None``.
    """
    rtnval = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == str(user_id))
        .first()
    )
    return rtnval


def _build_view(
        *,
        row: AuthApiToken,
        user: Optional[IdentityUser],
        now: datetime
    ) -> ApiTokenView:
    """
        Build the read model for a token row.

        :param row: Token row.
        :param user: The token's user (``None`` when the lookup
                     missed).
        :param now: Evaluation time for the status.

        :returns: :class:`ApiTokenView`.
    """
    login_name = user.login_name if user is not None else str(row.user_id)
    created_by = row.created_by_user_id
    rtnval = ApiTokenView(
        token_id=str(row.token_id),
        user_id=str(row.user_id),
        login_name=login_name,
        is_service_account=is_service_account(user=user),
        name=row.name,
        token_hint=row.token_hint,
        scope=row.scope,
        status=_token_status(row=row, now=now),
        created_at=_as_utc(row.created_at),
        created_by_user_id=str(created_by) if created_by is not None else None,
        expires_at=_as_utc(row.expires_at),
        last_used_at=_as_utc(row.last_used_at),
        revoked_at=_as_utc(row.revoked_at),
    )
    return rtnval


def _normalize_name(*, name: Any) -> str:
    """
        Validate and trim a token label.

        :param name: Caller-supplied label.

        :returns: Trimmed label.
        :raises: ApiTokenValidationError
    """
    if not isinstance(name, str) or len(name.strip()) == 0:
        raise ApiTokenValidationError("A token name is required.")
    trimmed = name.strip()
    if len(trimmed) > MAX_TOKEN_NAME_LENGTH:
        raise ApiTokenValidationError(
            "A token name may be at most {} characters.".format(MAX_TOKEN_NAME_LENGTH)
        )
    rtnval = trimmed
    return rtnval


def _normalize_lifetime_days(*, lifetime_days: Any) -> int:
    """
        Validate a token lifetime.

        :param lifetime_days: Days until expiry, or ``None`` for the
                              default.

        :returns: Lifetime in days.
        :raises: ApiTokenValidationError
    """
    if lifetime_days is None:
        return DEFAULT_TOKEN_LIFETIME_DAYS
    if isinstance(lifetime_days, bool):
        raise ApiTokenValidationError("expires_in_days must be a whole number of days.")
    try:
        parsed = int(str(lifetime_days).strip())
    except (TypeError, ValueError):
        raise ApiTokenValidationError(
            "expires_in_days must be a whole number of days."
        ) from None
    if parsed < 1 or parsed > MAX_TOKEN_LIFETIME_DAYS:
        raise ApiTokenValidationError(
            "expires_in_days must be between 1 and {}.".format(MAX_TOKEN_LIFETIME_DAYS)
        )
    rtnval = parsed
    return rtnval


def _normalize_scope(*, scope: Any) -> str:
    """
        Validate a token scope.

        :param scope: ``read-write``, ``read-only``, or ``None`` for the
                      default (``read-write``).

        :returns: The scope.
        :raises: ApiTokenValidationError
    """
    if scope is None or (isinstance(scope, str) and len(scope.strip()) == 0):
        return SCOPE_READ_WRITE
    if not isinstance(scope, str) or scope.strip() not in SUPPORTED_SCOPES:
        raise ApiTokenValidationError(
            "scope must be one of: {}.".format(", ".join(SUPPORTED_SCOPES))
        )
    rtnval = scope.strip()
    return rtnval


def _enqueue(*, db_session: DbSession, topic: str, payload: Dict[str, Any]) -> None:
    """
        Stage an entity event for publication after commit.

        :param db_session: Active SQLAlchemy session.
        :param topic: Event topic.
        :param payload: Event payload.

        :returns: None.
    """
    event = EntityEvent(topic=topic, payload=payload, source_event_id=new_uuid())
    enqueue_event(db_session=db_session, event=event)
    return


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def create_api_token(
        *,
        db_session: DbSession,
        user_id: str,
        name: Any,
        lifetime_days: Any,
        scope: Any,
        actor_user_id: Optional[str],
        now: Optional[datetime] = None
    ) -> IssuedApiToken:
    """
        Issue a token that acts as ``user_id`` and commit it.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The user (person or service account) the token
                        acts as. Must be active.
        :param name: Label, 1-128 characters.
        :param lifetime_days: Days until expiry (1-366); ``None`` for
                              :data:`DEFAULT_TOKEN_LIFETIME_DAYS`.
        :param scope: ``read-write`` (default) or ``read-only``.
        :param actor_user_id: Who is issuing the token.
        :param now: Evaluation time (tests).

        :returns: :class:`IssuedApiToken` carrying the secret once.
        :raises: ApiTokenValidationError
    """
    resolved_now = _resolve_now(now)
    token_name = _normalize_name(name=name)
    token_lifetime_days = _normalize_lifetime_days(lifetime_days=lifetime_days)
    token_scope = _normalize_scope(scope=scope)

    user = _load_user(db_session=db_session, user_id=user_id)
    if user is None:
        raise ApiTokenValidationError("The token's account does not exist.")
    if user.status != UserStatus.ACTIVE:
        raise ApiTokenValidationError(
            "The token's account is not active, so it cannot hold tokens."
        )

    token = generate_token_secret()
    row = AuthApiToken(
        token_id=new_uuid(),
        user_id=str(user.user_id),
        name=token_name,
        token_sha256=digest_token(token=token),
        token_hint=token[:len(TOKEN_PREFIX) + TOKEN_HINT_LENGTH],
        scope=token_scope,
        created_at=resolved_now,
        created_by_user_id=actor_user_id,
        expires_at=resolved_now + timedelta(days=token_lifetime_days),
        last_used_at=None,
        revoked_at=None,
        revoked_by_user_id=None,
    )
    db_session.add(row)
    db_session.flush()

    _enqueue(
        db_session=db_session,
        topic=ApiTokenEventTopics.TOKEN_CREATED,
        payload={
            "token_id": str(row.token_id),
            "user_id": str(row.user_id),
            "login_name": user.login_name,
            "is_service_account": is_service_account(user=user),
            "name": row.name,
            "scope": row.scope,
            "expires_at": _iso_or_none(row.expires_at),
            "created_at": _iso_or_none(row.created_at),
            "actor_user_id": actor_user_id,
            "target_ref": "api_token:{}".format(row.token_id),
        },
    )
    db_session.commit()

    view = _build_view(row=row, user=user, now=resolved_now)
    rtnval = IssuedApiToken(token=token, view=view)
    return rtnval


def list_api_tokens(
        *,
        db_session: DbSession,
        user_id: Optional[str],
        now: Optional[datetime] = None
    ) -> List[ApiTokenView]:
    """
        List tokens, newest first.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Only this user's tokens; ``None`` for every
                        token (administrators).
        :param now: Evaluation time for the status (tests).

        :returns: List of :class:`ApiTokenView`.
    """
    resolved_now = _resolve_now(now)
    query = db_session.query(AuthApiToken)
    if user_id is not None:
        query = query.filter(AuthApiToken.user_id == str(user_id))
    rows = query.all()
    rows.sort(
        key=lambda candidate: _as_utc(candidate.created_at) or resolved_now,
        reverse=True,
    )

    users_by_id: Dict[str, IdentityUser] = {}
    user_ids = sorted(set(str(row.user_id) for row in rows))
    if len(user_ids) > 0:
        for user in db_session.query(IdentityUser).filter(IdentityUser.user_id.in_(user_ids)).all():
            users_by_id[str(user.user_id)] = user

    views: List[ApiTokenView] = []
    for row in rows:
        user = users_by_id.get(str(row.user_id), None)
        views.append(_build_view(row=row, user=user, now=resolved_now))
    rtnval = views
    return rtnval


def read_api_token(
        *,
        db_session: DbSession,
        token_id: str,
        owner_user_id: Optional[str] = None,
        now: Optional[datetime] = None
    ) -> ApiTokenView:
    """
        Read one token.

        :param db_session: Active SQLAlchemy session.
        :param token_id: Token id.
        :param owner_user_id: When set, the token must act as this user
                              (a caller managing their own tokens); a
                              token of anyone else reads as not found.
        :param now: Evaluation time (tests).

        :returns: :class:`ApiTokenView`.
        :raises: ApiTokenNotFoundError
    """
    resolved_now = _resolve_now(now)
    row = _load_token_row(db_session=db_session, token_id=token_id, owner_user_id=owner_user_id)
    user = _load_user(db_session=db_session, user_id=row.user_id)
    rtnval = _build_view(row=row, user=user, now=resolved_now)
    return rtnval


def _load_token_row(
        *,
        db_session: DbSession,
        token_id: str,
        owner_user_id: Optional[str]
    ) -> AuthApiToken:
    """
        Load a token row, optionally scoped to its owner.

        :param db_session: Active SQLAlchemy session.
        :param token_id: Token id.
        :param owner_user_id: Required owner, or ``None``.

        :returns: The row.
        :raises: ApiTokenNotFoundError
    """
    row = None
    if isinstance(token_id, str) and len(token_id.strip()) > 0:
        try:
            row = (
                db_session.query(AuthApiToken)
                .filter(AuthApiToken.token_id == token_id.strip())
                .first()
            )
        except (ValueError, TypeError):
            # A malformed id cannot name a token.
            row = None
    if row is not None and owner_user_id is not None:
        if str(row.user_id) != str(owner_user_id):
            row = None
    if row is None:
        err_msg_lines = ["API token not found."]
        err_msg_lines.append("TOKEN_ID: {}".format(token_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ApiTokenNotFoundError(err_msg) from None
    rtnval = row
    return rtnval


def revoke_api_token(
        *,
        db_session: DbSession,
        token_id: str,
        actor_user_id: Optional[str],
        owner_user_id: Optional[str] = None,
        now: Optional[datetime] = None
    ) -> ApiTokenView:
    """
        Revoke a token and commit. Revoking a token that is already
        revoked changes nothing and records nothing.

        :param db_session: Active SQLAlchemy session.
        :param token_id: Token id.
        :param actor_user_id: Who is revoking it.
        :param owner_user_id: When set, only a token acting as this
                              user may be revoked (self-service).
        :param now: Evaluation time (tests).

        :returns: The token's view after revocation.
        :raises: ApiTokenNotFoundError
    """
    resolved_now = _resolve_now(now)
    row = _load_token_row(db_session=db_session, token_id=token_id, owner_user_id=owner_user_id)
    user = _load_user(db_session=db_session, user_id=row.user_id)

    if row.revoked_at is None:
        row.revoked_at = resolved_now
        row.revoked_by_user_id = actor_user_id
        db_session.flush()
        _enqueue(
            db_session=db_session,
            topic=ApiTokenEventTopics.TOKEN_REVOKED,
            payload={
                "token_id": str(row.token_id),
                "user_id": str(row.user_id),
                "login_name": user.login_name if user is not None else None,
                "name": row.name,
                "revoked_at": _iso_or_none(resolved_now),
                "actor_user_id": actor_user_id,
                "target_ref": "api_token:{}".format(row.token_id),
            },
        )
        db_session.commit()

    rtnval = _build_view(row=row, user=user, now=resolved_now)
    return rtnval


def revoke_tokens_for_user(
        *,
        db_session: DbSession,
        user_id: str,
        actor_user_id: Optional[str],
        now: Optional[datetime] = None
    ) -> int:
    """
        Revoke every token that acts as ``user_id`` and commit.

        :param db_session: Active SQLAlchemy session.
        :param user_id: The user whose tokens to revoke.
        :param actor_user_id: Who is revoking them.
        :param now: Evaluation time (tests).

        :returns: Number of tokens revoked.
    """
    resolved_now = _resolve_now(now)
    rows = (
        db_session.query(AuthApiToken)
        .filter(AuthApiToken.user_id == str(user_id))
        .filter(AuthApiToken.revoked_at.is_(None))
        .all()
    )
    for row in rows:
        row.revoked_at = resolved_now
        row.revoked_by_user_id = actor_user_id
        _enqueue(
            db_session=db_session,
            topic=ApiTokenEventTopics.TOKEN_REVOKED,
            payload={
                "token_id": str(row.token_id),
                "user_id": str(row.user_id),
                "login_name": None,
                "name": row.name,
                "revoked_at": _iso_or_none(resolved_now),
                "actor_user_id": actor_user_id,
                "target_ref": "api_token:{}".format(row.token_id),
            },
        )
    if len(rows) > 0:
        db_session.flush()
        db_session.commit()
    rtnval = len(rows)
    return rtnval


def _use_audit_window(*, when: datetime) -> int:
    """
        Index of the :data:`USE_AUDIT_INTERVAL_SECONDS`-long window
        (aligned to the Unix epoch, so hourly windows are clock hours
        in UTC) that ``when`` falls in.

        :param when: Aware datetime.

        :returns: Window index.
    """
    rtnval = int(when.timestamp()) // USE_AUDIT_INTERVAL_SECONDS
    return rtnval


def _reject(*, reason: str) -> None:
    """
        Raise :class:`ApiTokenRejectedError` with one generic message
        and a specific ``reason`` for logs.

        :param reason: ``unknown`` / ``revoked`` / ``expired`` /
                       ``account_inactive``.

        :returns: Never returns.
        :raises: ApiTokenRejectedError
    """
    raise ApiTokenRejectedError(
        "The API token is invalid, expired, or revoked.", reason=reason
    ) from None


def authenticate_api_token(
        *,
        db_session: DbSession,
        token: str,
        now: datetime,
        request_method: str,
        request_path: str
    ) -> ApiTokenPrincipal:
    """
        Authenticate a presented token and return its principal.

        Records the use: ``last_used_at`` is refreshed when it is more
        than :data:`LAST_USED_WRITE_INTERVAL_SECONDS` old, and an
        ``entity.api_token.used`` event (captured into the audit
        store) is published on the token's first use and then on its
        first use in each :data:`USE_AUDIT_INTERVAL_SECONDS` window
        (each clock hour, UTC). Those writes are committed here,
        before the request's handler runs, so a read-only request
        still records its use.

        :param db_session: Active SQLAlchemy session.
        :param token: The bearer value.
        :param now: Evaluation time.
        :param request_method: HTTP method (for the audit record).
        :param request_path: Request path (for the audit record).

        :returns: :class:`ApiTokenPrincipal`.
        :raises: ApiTokenRejectedError
    """
    resolved_now = _resolve_now(now)
    if looks_like_api_token(candidate=token) is False:
        _reject(reason="malformed")

    row = (
        db_session.query(AuthApiToken)
        .filter(AuthApiToken.token_sha256 == digest_token(token=token))
        .first()
    )
    if row is None:
        _reject(reason="unknown")
    if row.revoked_at is not None:
        _reject(reason="revoked")
    expires_at = _as_utc(row.expires_at)
    if expires_at is None or expires_at <= resolved_now:
        _reject(reason="expired")

    user = _load_user(db_session=db_session, user_id=row.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        _reject(reason="account_inactive")

    previous_use = _as_utc(row.last_used_at)
    record_use = False
    if previous_use is None:
        record_use = True
    elif _use_audit_window(when=previous_use) != _use_audit_window(when=resolved_now):
        # First use in a new audit window. Comparing windows (not the
        # gap since ``last_used_at``, which a busy token refreshes every
        # minute) keeps a continuously used token audited once a window.
        record_use = True

    refresh_last_used = record_use
    if previous_use is not None and (resolved_now - previous_use).total_seconds() >= LAST_USED_WRITE_INTERVAL_SECONDS:
        refresh_last_used = True

    if refresh_last_used is True:
        row.last_used_at = resolved_now
        db_session.flush()
        if record_use is True:
            _enqueue(
                db_session=db_session,
                topic=ApiTokenEventTopics.TOKEN_USED,
                payload={
                    "token_id": str(row.token_id),
                    "user_id": str(row.user_id),
                    "login_name": user.login_name,
                    "name": row.name,
                    "method": str(request_method).upper(),
                    "path": str(request_path),
                    "used_at": _iso_or_none(resolved_now),
                    "actor_user_id": str(row.user_id),
                    "target_ref": "api_token:{}".format(row.token_id),
                },
            )
        db_session.commit()

    rtnval = ApiTokenPrincipal(
        user_id=str(row.user_id),
        session_id=API_TOKEN_SESSION_ID_PREFIX + str(row.token_id),
        provider_kind=AuthProviderKind.LOCAL,
        provider_name=API_TOKEN_PROVIDER_NAME,
        token_id=str(row.token_id),
        token_name=row.name,
        token_scope=row.scope,
        token_expires_at=expires_at,
    )
    return rtnval


def token_scope_permits(*, principal: Any, method: str) -> bool:
    """
        Whether a principal's token scope lets it use ``method``.
        Principals that did not authenticate with a token are not
        restricted here.

        :param principal: Request principal (any kind) or ``None``.
        :param method: HTTP method.

        :returns: ``False`` only for a ``read-only`` token and an
                  unsafe method.
    """
    scope = getattr(principal, "token_scope", None)
    if scope != SCOPE_READ_ONLY:
        return True
    rtnval = str(method).upper() in SAFE_HTTP_METHODS
    return rtnval


# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------


def create_service_account(
        *,
        db_session: DbSession,
        login_name: Any,
        display_name: Any,
        actor_user_id: Optional[str]
    ) -> IdentityUser:
    """
        Create a service account (an identity user with no password,
        marked by :data:`SERVICE_ACCOUNT_PROVISIONING_SOURCE`) and
        commit. The creation is audited through the ordinary
        ``entity.user.created`` event.

        :param db_session: Active SQLAlchemy session.
        :param login_name: Login name: lower-case letters, digits,
                           ``.``, ``_`` and ``-``; 2-63 characters.
        :param display_name: Optional display name.
        :param actor_user_id: Who is creating it.

        :returns: The new :class:`IdentityUser`.
        :raises: ApiTokenValidationError (bad name or name taken)
    """
    from ccai.pychestrate.webservice.identity.users import user_service  # noqa: E402
    from ccai.pychestrate.webservice.identity.users.exceptions import (  # noqa: E402
        UserAlreadyExistsError,
    )

    if not isinstance(login_name, str):
        raise ApiTokenValidationError("A service account login name is required.")
    normalized_login = login_name.strip().lower()
    if _SERVICE_ACCOUNT_LOGIN_PATTERN.match(normalized_login) is None:
        raise ApiTokenValidationError(
            "A service account login name is 2-63 characters of lower-case"
            " letters, digits, '.', '_' or '-', starting with a letter or digit."
        )
    resolved_display_name = display_name.strip() if isinstance(display_name, str) else ""
    if len(resolved_display_name) == 0:
        resolved_display_name = normalized_login

    try:
        user = user_service.create_user(
            db_session=db_session,
            login_name=normalized_login,
            primary_email="{}@{}".format(normalized_login, SERVICE_ACCOUNT_EMAIL_DOMAIN),
            display_name=resolved_display_name,
            timezone="UTC",
            provisioning_source=SERVICE_ACCOUNT_PROVISIONING_SOURCE,
            external_id=None,
            actor_user_id=actor_user_id,
        )
    except UserAlreadyExistsError:
        db_session.rollback()
        raise ApiTokenValidationError(
            "An account named '{}' already exists.".format(normalized_login)
        ) from None
    rtnval = user
    return rtnval


def read_service_account(*, db_session: DbSession, user_id: str) -> IdentityUser:
    """
        Load a service account.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Identity user id.

        :returns: The :class:`IdentityUser`.
        :raises: ServiceAccountNotFoundError
    """
    user = None
    if isinstance(user_id, str) and len(user_id.strip()) > 0:
        try:
            user = _load_user(db_session=db_session, user_id=user_id.strip())
        except (ValueError, TypeError):
            user = None
    if user is None or is_service_account(user=user) is False:
        err_msg_lines = ["Service account not found."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ServiceAccountNotFoundError(err_msg) from None
    rtnval = user
    return rtnval


def list_service_accounts(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None
    ) -> List[ServiceAccountView]:
    """
        List every service account with its count of working tokens.

        :param db_session: Active SQLAlchemy session.
        :param now: Evaluation time (tests).

        :returns: List of :class:`ServiceAccountView`, by login name.
    """
    resolved_now = _resolve_now(now)
    users = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.provisioning_source == SERVICE_ACCOUNT_PROVISIONING_SOURCE)
        .all()
    )
    users.sort(key=lambda candidate: candidate.login_name)

    active_counts: Dict[str, int] = {}
    user_ids = [str(user.user_id) for user in users]
    if len(user_ids) > 0:
        rows = db_session.query(AuthApiToken).filter(AuthApiToken.user_id.in_(user_ids)).all()
        for row in rows:
            if _token_status(row=row, now=resolved_now) == TOKEN_STATUS_ACTIVE:
                key = str(row.user_id)
                active_counts[key] = active_counts.get(key, 0) + 1

    views: List[ServiceAccountView] = []
    for user in users:
        views.append(
            ServiceAccountView(
                user_id=str(user.user_id),
                login_name=user.login_name,
                display_name=user.display_name,
                status=user.status.value if user.status is not None else "",
                created_at=_as_utc(user.created_at),
                active_token_count=active_counts.get(str(user.user_id), 0),
            )
        )
    rtnval = views
    return rtnval


__all__ = [
    "API_TOKEN_PROVIDER_NAME",
    "API_TOKEN_SESSION_ID_PREFIX",
    "ApiTokenPrincipal",
    "ApiTokenView",
    "DEFAULT_TOKEN_LIFETIME_DAYS",
    "IssuedApiToken",
    "LAST_USED_WRITE_INTERVAL_SECONDS",
    "MAX_TOKEN_LIFETIME_DAYS",
    "SAFE_HTTP_METHODS",
    "SCOPE_READ_ONLY",
    "SCOPE_READ_WRITE",
    "SERVICE_ACCOUNT_EMAIL_DOMAIN",
    "SERVICE_ACCOUNT_PROVISIONING_SOURCE",
    "SUPPORTED_SCOPES",
    "ServiceAccountView",
    "TOKEN_PREFIX",
    "TOKEN_STATUS_ACTIVE",
    "TOKEN_STATUS_EXPIRED",
    "TOKEN_STATUS_REVOKED",
    "USE_AUDIT_INTERVAL_SECONDS",
    "authenticate_api_token",
    "create_api_token",
    "create_service_account",
    "digest_token",
    "generate_token_secret",
    "is_service_account",
    "list_api_tokens",
    "list_service_accounts",
    "looks_like_api_token",
    "read_api_token",
    "read_service_account",
    "revoke_api_token",
    "revoke_tokens_for_user",
    "token_scope_permits",
]
