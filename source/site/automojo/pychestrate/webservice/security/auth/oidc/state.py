"""
.. module:: security.auth.oidc.state
    :synopsis: auth_oidc_state row helpers.

The ``auth_oidc_state`` table is a one-shot per-flow row.
Operations land here:

* :func:`insert_state` — seat a fresh row at begin-login
  time.
* :func:`consume_state` — atomically read and delete a row
  by its state key. Returns ``None`` when the state is
  unknown (forged callback) or expired (replay against an
  old flow).
* :func:`sweep_expired` — background helper that drops
  rows past their TTL.

Rows are short-lived (default 10 minutes per the OIDC
spec). The pkce_verifier_enc column persists raw verifier
bytes in M2; the M3 hardening pass layers KEK encryption.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import secrets

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.security.auth.models import AuthOidcState


DEFAULT_STATE_TTL = timedelta(minutes=10)


def generate_state_token() -> str:
    """
        Build a fresh URL-safe state token used to bind the
        IdP redirect back to the originating flow row.
        Returns a 43-character base64url string (32 bytes
        of entropy).
    """
    raw = secrets.token_urlsafe(32)
    return raw


def generate_nonce() -> str:
    """
        Build a fresh URL-safe nonce used to bind the
        ``id_token`` returned by the IdP to the originating
        flow row.
    """
    raw = secrets.token_urlsafe(32)
    return raw


@dataclass(frozen=True)
class StateRecord:
    """
        Caller-facing read-model of an auth_oidc_state row.
    """
    state: str
    nonce: str
    pkce_verifier: bytes
    provider_name: str
    redirect_target: str
    created_at: datetime
    expires_at: datetime


def insert_state(
        *,
        db_session: DbSession,
        state: str,
        nonce: str,
        pkce_verifier: bytes,
        provider_name: str,
        redirect_target: str = "",
        ttl: Optional[timedelta] = None,
        now: Optional[datetime] = None
    ) -> AuthOidcState:
    """
        Persist a one-shot auth_oidc_state row.

        :raises: ValueError on empty state / nonce / pkce
                 / provider_name.
    """
    if state is None or len(state) == 0:
        raise ValueError("insert_state requires a non-empty state.")
    if nonce is None or len(nonce) == 0:
        raise ValueError("insert_state requires a non-empty nonce.")
    if pkce_verifier is None or len(pkce_verifier) == 0:
        raise ValueError("insert_state requires non-empty pkce_verifier.")
    if provider_name is None or len(provider_name) == 0:
        raise ValueError("insert_state requires a non-empty provider_name.")

    materialized_now = now if now is not None else utc_now()
    materialized_ttl = ttl if ttl is not None else DEFAULT_STATE_TTL
    row = AuthOidcState(
        state=state,
        nonce=nonce,
        pkce_verifier_enc=pkce_verifier,
        provider_name=provider_name,
        created_at=materialized_now,
        expires_at=materialized_now + materialized_ttl,
        redirect_target=redirect_target or "",
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return row


def consume_state(
        *,
        db_session: DbSession,
        state: str,
        now: Optional[datetime] = None
    ) -> Optional[StateRecord]:
    """
        Atomically read and remove the auth_oidc_state row
        keyed by ``state``. Returns ``None`` when the state
        is unknown or expired — the caller surfaces a 401
        without leaking which case applied.
    """
    row = (
        db_session.query(AuthOidcState)
        .filter(AuthOidcState.state == state)
        .first()
    )
    if row is None:
        return None
    materialized_now = now if now is not None else utc_now()
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    captured = StateRecord(
        state=row.state,
        nonce=row.nonce,
        pkce_verifier=bytes(row.pkce_verifier_enc),
        provider_name=row.provider_name,
        redirect_target=row.redirect_target or "",
        created_at=row.created_at,
        expires_at=row.expires_at,
    )
    db_session.delete(row)
    db_session.flush()
    db_session.commit()
    if materialized_now > expires:
        return None
    return captured


def sweep_expired(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None
    ) -> int:
    """
        Drop every auth_oidc_state row past its
        ``expires_at`` deadline. Returns the count removed
        for operator metrics.
    """
    materialized_now = now if now is not None else utc_now()
    rows = (
        db_session.query(AuthOidcState)
        .all()
    )
    removed = 0
    for row in rows:
        deadline = row.expires_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if materialized_now <= deadline:
            continue
        db_session.delete(row)
        removed = removed + 1
    db_session.flush()
    db_session.commit()
    return removed
