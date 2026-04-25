"""
.. module:: webhooks_in.replay_cache
    :synopsis: De-duplicate inbound deliveries by their provider id.

The replay cache turns the dispatcher into an at-most-once
publisher across retries. M1 stores rows in
``webhooks_in_seen_deliveries`` with a 72 hour TTL; the M2
sweeper deletes expired rows. Concurrent inserts on the same
``(provider, hook_name, delivery_id)`` lose the PK race and
report ``replay_ignored``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.webhooks_in import repository


SEEN_TTL_HOURS: int = 72


class ReplayOutcome(str, enum.Enum):
    """
        Result of a replay-cache lookup-and-record.
    """
    RECORDED = "recorded"
    REPLAY_IGNORED = "replay_ignored"


def record_delivery_or_replay(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str,
        delivery_id: str,
        now: Optional[datetime] = None
    ) -> ReplayOutcome:
    """
        Insert a seen-delivery row atomically.

        :param db_session: Open DB session; the caller owns the
                           outer transaction commit.
        :param provider: Parser factory name.
        :param hook_name: Per-project nickname.
        :param delivery_id: Provider-native delivery id; opaque
                            string treated as part of the
                            composite PK.
        :param now: Optional override timestamp; defaults to
                    :func:`datetime.utcnow`.

        :returns: :data:`ReplayOutcome.RECORDED` on first sight,
                  :data:`ReplayOutcome.REPLAY_IGNORED` on a
                  duplicate.
    """
    when = now if now is not None else datetime.now(tz=timezone.utc)
    expires = when + timedelta(hours=SEEN_TTL_HOURS)

    # Optimistic check first. The cache table is small relative
    # to the request volume so the read is cheap. The PK
    # constraint provides the ultimate safety net under
    # concurrent writers.
    existing = repository.find_seen_delivery(
        db_session=db_session,
        provider=provider,
        hook_name=hook_name,
        delivery_id=delivery_id,
    )
    if existing is not None:
        rtnval = ReplayOutcome.REPLAY_IGNORED
        return rtnval

    try:
        repository.insert_seen_delivery(
            db_session=db_session,
            provider=provider,
            hook_name=hook_name,
            delivery_id=delivery_id,
            first_seen_at=when,
            expires_at=expires,
        )
    except IntegrityError:
        # Concurrent writer beat us to the PK; roll back the
        # half-written insert so the outer transaction stays
        # usable.
        db_session.rollback()
        rtnval = ReplayOutcome.REPLAY_IGNORED
        return rtnval

    rtnval = ReplayOutcome.RECORDED
    return rtnval
