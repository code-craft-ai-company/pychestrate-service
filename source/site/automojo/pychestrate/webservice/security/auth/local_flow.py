"""
.. module:: security.auth.local_flow
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Local credential verification with pluggable hashing and backoff.

.. moduleauthor:: Automation Mojo LLC

The verifier never imports a specific hashing library. It resolves a
``password_hasher`` factory implementation through the extension host
and delegates hashing and verification to it. Operators who want
Argon2id install a ``pychestrate-ext-auth-argon2id`` extension pack
that registers at a lower ``PRECEDENCE`` than the in-tree stdlib
reference. Old rows hashed under a previous algorithm continue to
verify through the algorithm-name lookup path
(:func:`resolve_hasher_for_verifying`).

NFR-2's specific Argon2id parameters (memory ≥ 64 MiB, iterations ≥ 3)
are enforced by whichever hasher the operator registers at the top of
the precedence chain — the service has no opinion about which hasher
those parameters belong to.

The verifier still owns:

- Password pepper lookup via :mod:`pepper_loader`.
- Exponential backoff keyed on ``(login_name, source_ip)`` with a
  ``2**n`` delay clamped to 300 s and a 900 s sliding reset window.
- Identity-user status checks (only ``UserStatus.ACTIVE`` may authenticate).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from automojo.pychestrate.webservice.security.auth.exceptions import AuthenticationError
from automojo.pychestrate.webservice.security.auth.factories.password_hasher import (
    EncodedHash,
    resolve_hasher_for_hashing,
    resolve_hasher_for_verifying,
)
from automojo.pychestrate.webservice.security.auth.models import AuthLocalCredentials
from automojo.pychestrate.webservice.security.auth.pepper_loader import get_active_pepper


logger = logging.getLogger(__name__)


BACKOFF_BASE_DELAY_SECONDS: float = 1.0
BACKOFF_MAX_DELAY_SECONDS: float = 300.0
BACKOFF_RESET_AFTER_SECONDS: float = 900.0


@dataclass(frozen=True)
class LocalCredentialsResult:
    """
        The outcome of a successful local credential verification.

        :param user_id: Resolved identity user id.
    """
    user_id: str


@dataclass
class _BackoffState:
    """
        Mutable backoff counter for a (login_name, source_ip) key.

        :param failure_count: Consecutive failures since last success.
        :param blocked_until: UTC timestamp before which further attempts
                              are rejected without hashing.
        :param updated_at: Last update timestamp (used for decay).
    """
    failure_count: int
    blocked_until: datetime
    updated_at: datetime


_BACKOFF_LOCK = threading.RLock()
_BACKOFF_STATE: Dict[Tuple[str, str], _BackoffState] = {}


def hash_password(*, password: str) -> Tuple[bytes, dict]:
    """
        Hash a password using the currently-highest-priority registered
        ``password_hasher`` implementation.

        :param password: Plaintext password.

        :returns: Tuple of ``(encoded_hash_bytes, algo_params_dict)`` ready
                  for persistence on an ``AuthLocalCredentials`` row.
        :raises: ConfigurationError when no hasher is registered.
    """
    hasher = resolve_hasher_for_hashing()
    pepper = get_active_pepper()
    encoded: EncodedHash = hasher.hash_password(password=password, pepper=pepper)
    rtnval = (encoded.encoded_bytes, dict(encoded.algo_params))
    return rtnval


def _current_backoff_delay(*, failure_count: int) -> float:
    """
        Compute the next backoff delay from the failure counter.

        :param failure_count: Running failure count.

        :returns: Clamped delay in seconds.
    """
    delay = BACKOFF_BASE_DELAY_SECONDS * (2 ** max(failure_count - 1, 0))
    if delay > BACKOFF_MAX_DELAY_SECONDS:
        delay = BACKOFF_MAX_DELAY_SECONDS
    return delay


def _check_and_mark_backoff(*, login_name: str, source_ip: str, now: datetime) -> None:
    """
        Raise :class:`AuthenticationError` when the caller is still in a
        backoff window, otherwise allow the attempt to proceed.

        :param login_name: Claimed login_name.
        :param source_ip: Remote IP string for keying.
        :param now: Evaluation timestamp.

        :returns: None.
        :raises: AuthenticationError
    """
    key = (login_name, source_ip)
    with _BACKOFF_LOCK:
        state = _BACKOFF_STATE.get(key, None)
        if state is None:
            return
        if now < state.blocked_until:
            raise AuthenticationError("Too many recent failures; try again later")

        age = (now - state.updated_at).total_seconds()
        if age > BACKOFF_RESET_AFTER_SECONDS:
            _BACKOFF_STATE.pop(key, None)
    return


def _record_backoff_failure(*, login_name: str, source_ip: str, now: datetime) -> None:
    """
        Increment the failure counter and schedule the next allowed attempt.

        :param login_name: Claimed login_name.
        :param source_ip: Remote IP string.
        :param now: Evaluation timestamp.

        :returns: None.
    """
    key = (login_name, source_ip)
    with _BACKOFF_LOCK:
        state = _BACKOFF_STATE.get(key, None)
        if state is None:
            state = _BackoffState(failure_count=0, blocked_until=now, updated_at=now)

        new_count = state.failure_count + 1
        delay_seconds = _current_backoff_delay(failure_count=new_count)
        _BACKOFF_STATE[key] = _BackoffState(
            failure_count=new_count,
            blocked_until=now + timedelta(seconds=delay_seconds),
            updated_at=now,
        )
    return


def _record_backoff_success(*, login_name: str, source_ip: str) -> None:
    """
        Clear the failure counter after a successful verification.

        :param login_name: Claimed login_name.
        :param source_ip: Remote IP string.

        :returns: None.
    """
    key = (login_name, source_ip)
    with _BACKOFF_LOCK:
        _BACKOFF_STATE.pop(key, None)
    return


def reset_backoff_for_testing() -> None:
    """
        Clear every backoff entry. Test-only helper.

        :returns: None.
    """
    with _BACKOFF_LOCK:
        _BACKOFF_STATE.clear()
    return


def _verify_stored_hash(
        *,
        stored_hash: bytes,
        algo_params: dict,
        password: str
    ) -> bool:
    """
        Verify a stored encoded hash against ``password`` by looking up the
        hasher whose ``algorithm_name`` matches the stored ``algo_params``.

        :param stored_hash: Encoded hash bytes from
                            ``AuthLocalCredentials.argon2id_hash``.
        :param algo_params: Stored ``algo_params`` dict from the same row.
        :param password: Submitted plaintext password.

        :returns: True on match, False otherwise.
    """
    algorithm_name = ""
    if algo_params is not None:
        candidate = algo_params.get("algorithm", "")
        if candidate is not None:
            algorithm_name = str(candidate)

    hasher = resolve_hasher_for_verifying(algorithm_name=algorithm_name)
    pepper = get_active_pepper()

    try:
        rtnval = hasher.verify_password(
            encoded_hash=stored_hash,
            password=password,
            pepper=pepper,
        )
    except Exception as xcpt:  # noqa: BLE001 — hasher failures must not crash login
        logger.info(
            "local_flow.verify_hasher_failed algorithm=%s error=%s",
            algorithm_name, xcpt,
        )
        return False

    return rtnval


def verify_local_credentials(
        *,
        login_name: str,
        password: str,
        mfa_code: Optional[str],
        source_ip: str,
        db_session: Optional[DbSession] = None
    ) -> LocalCredentialsResult:
    """
        Verify local credentials using the registered ``password_hasher``
        and enforce the exponential backoff window.

        :param login_name: Claimed login name; normalized to lower case.
        :param password: Submitted plaintext password.
        :param mfa_code: Optional MFA response — present when a partial
                         session has already been opened and the second
                         factor is required before full login.
        :param source_ip: Remote IP used for backoff keying.
        :param db_session: Active SQLAlchemy session. When None, the
                           function raises :class:`ConfigurationError` —
                           callers are expected to pass the per-request
                           session.

        :returns: :class:`LocalCredentialsResult` on success.
        :raises: AuthenticationError, MfaRequiredError, ConfigurationError
    """
    if db_session is None:
        raise ConfigurationError(
            "verify_local_credentials requires an active db_session; the caller "
            "is expected to pass the per-request SQLAlchemy session."
        )

    if login_name is None or len(login_name.strip()) == 0:
        raise AuthenticationError("Missing login_name")
    if password is None or len(password) == 0:
        raise AuthenticationError("Missing password")

    normalized_login = login_name.strip().lower()
    now = datetime.now(timezone.utc)

    _check_and_mark_backoff(login_name=normalized_login, source_ip=source_ip, now=now)

    user = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.login_name == normalized_login)
        .first()
    )
    credentials: Optional[AuthLocalCredentials] = None
    if user is not None:
        credentials = (
            db_session.query(AuthLocalCredentials)
            .filter(AuthLocalCredentials.user_id == user.user_id)
            .first()
        )

    if user is None or credentials is None:
        _record_backoff_failure(login_name=normalized_login, source_ip=source_ip, now=now)
        raise AuthenticationError("Invalid credentials")

    if user.status != UserStatus.ACTIVE:
        _record_backoff_failure(login_name=normalized_login, source_ip=source_ip, now=now)
        raise AuthenticationError("Account is not active")

    matched = _verify_stored_hash(
        stored_hash=bytes(credentials.argon2id_hash),
        algo_params=credentials.algo_params or {},
        password=password,
    )
    if matched is False:
        _record_backoff_failure(login_name=normalized_login, source_ip=source_ip, now=now)
        raise AuthenticationError("Invalid credentials")

    _record_backoff_success(login_name=normalized_login, source_ip=source_ip)

    rtnval = LocalCredentialsResult(user_id=str(user.user_id))
    return rtnval
