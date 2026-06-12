"""
.. module:: resources.scheduler.service
    :synopsis: Scheduler facade — enqueue / cancel / pick / dispatch.

M1 ships a synchronous, hard-wired FIFO surface. Calls into this
module persist a :class:`SchedulerEntry` row and emit
``pychestrate.scheduler.{enqueued,cancelled,dispatched}`` events.

The async dispatch worker, the per-pool algorithm registry, and the
starvation sweep land in M2. The columns required by those features
(``priority``, ``fair_share_*``, ``deadline_at``, ``promoted_at``)
already persist so the M2 upgrade is purely additive.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.scheduler import repository
from ccai.pychestrate.webservice.resources.scheduler.errors import (
    SchedulerAspectsInvalidError,
    SchedulerEntryConflictError,
    SchedulerEntryNotFoundError,
)
from ccai.pychestrate.webservice.resources.scheduler.events import (
    SchedulerEventTopics,
)
from ccai.pychestrate.webservice.resources.scheduler.models import (
    SchedulerEntry,
    SchedulerEntryState,
)


DEFAULT_ALGORITHM: str = "fifo"
DEFAULT_PRIORITY: int = 50
DEFAULT_FAIR_SHARE_WEIGHT: float = 1.0
PRIORITY_MIN: int = 0
PRIORITY_MAX: int = 100
FAIR_SHARE_WEIGHT_MIN_EXCLUSIVE: float = 0.0
FAIR_SHARE_WEIGHT_MAX: float = 10.0


@dataclass(frozen=True)
class SchedulerAspects:
    """
        Caller-tunable knobs persisted on the entry row.

        :param algorithm: Pool's configured algorithm at enqueue
                          time. M1 ignores at dispatch (FIFO is
                          hard-wired); the value is recorded for
                          M2 algorithm-aware scheduling.
        :param priority: 0..100, 0 highest. Clamped during
                         normalization.
        :param fair_share_key: Optional key the M2 fair-share
                               scheduler aggregates running-time
                               against.
        :param fair_share_weight: (0, 10]. Clamped during
                                  normalization.
        :param deadline_at: Caller's hard deadline. Used by the
                            M2 deadline scheduler and the
                            starvation sweep.
    """
    algorithm: str = DEFAULT_ALGORITHM
    priority: int = DEFAULT_PRIORITY
    fair_share_key: Optional[str] = None
    fair_share_weight: float = DEFAULT_FAIR_SHARE_WEIGHT
    deadline_at: Optional[datetime] = None


@dataclass(frozen=True)
class SchedulerEntryView:
    """
        Read-model returned to callers.
    """
    entry_id: str
    reservation_id: str
    pool_id: str
    project_id: str
    algorithm: str
    priority: int
    fair_share_key: Optional[str]
    fair_share_weight: float
    deadline_at: Optional[datetime]
    enqueued_at: datetime
    promoted_at: Optional[datetime]
    dispatched_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    state: SchedulerEntryState


def enqueue(
        *,
        db_session: DbSession,
        reservation_id: str,
        pool_id: str,
        project_id: str,
        aspects: Optional[SchedulerAspects] = None
    ) -> SchedulerEntryView:
    """
        Persist a queued reservation in the scheduler. Idempotent
        on a previously-enqueued reservation that is still queued
        — the existing view is returned. A non-queued prior entry
        (dispatched or cancelled) raises
        :class:`SchedulerEntryConflictError` so callers cannot
        re-enqueue something that already left the queue.

        :raises: SchedulerAspectsInvalidError on bad aspects;
                 SchedulerEntryConflictError on terminal duplicate.
    """
    effective = aspects or SchedulerAspects()
    _validate_aspects(aspects=effective)

    existing = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if existing is not None:
        if existing.state == SchedulerEntryState.QUEUED:
            rtnval = _to_view(row=existing)
            return rtnval
        err_lines = ["Reservation already has a terminal scheduler entry."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_lines.append("ENTRY_ID: {}".format(existing.entry_id))
        err_lines.append("STATE: {}".format(existing.state.value))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerEntryConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_entry(
        db_session=db_session,
        reservation_id=reservation_id,
        pool_id=pool_id,
        project_id=project_id,
        algorithm=effective.algorithm,
        priority=effective.priority,
        fair_share_key=effective.fair_share_key,
        fair_share_weight=effective.fair_share_weight,
        deadline_at=effective.deadline_at,
        enqueued_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SchedulerEventTopics.ENQUEUED,
            payload={
                "entry_id": str(row.entry_id),
                "reservation_id": reservation_id,
                "pool_id": pool_id,
                "project_id": project_id,
                "algorithm": effective.algorithm,
                "priority": effective.priority,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def cancel(
        *,
        db_session: DbSession,
        reservation_id: str,
        actor: Optional[str] = None
    ) -> SchedulerEntryView:
    """
        Cancel a queued entry. Idempotent on already-cancelled or
        already-dispatched entries — the existing view is
        returned.

        :raises: SchedulerEntryNotFoundError when no entry exists
                 for the reservation.
    """
    row = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["No scheduler entry for reservation."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerEntryNotFoundError(err_msg) from None

    if row.state in (
        SchedulerEntryState.CANCELLED,
        SchedulerEntryState.DISPATCHED,
    ):
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = SchedulerEntryState.CANCELLED
    row.cancelled_at = now
    row.version = row.version + 1
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SchedulerEventTopics.CANCELLED,
            payload={
                "entry_id": str(row.entry_id),
                "reservation_id": str(row.reservation_id),
                "pool_id": str(row.pool_id),
                "actor": actor,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def pick_next_for_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> Optional[SchedulerEntryView]:
    """
        Return the next queued entry for ``pool_id`` per the
        hard-wired FIFO algorithm. Returns ``None`` when the
        queue is empty. Pure read — does not transition state.
    """
    row = repository.find_next_queued_for_pool(
        db_session=db_session, pool_id=pool_id,
    )
    if row is None:
        return None
    rtnval = _to_view(row=row)
    return rtnval


def mark_dispatched(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> SchedulerEntryView:
    """
        Transition a queued entry to ``DISPATCHED``. Called by the
        checkout module after a queued reservation is granted.
        Idempotent on already-dispatched entries.

        :raises: SchedulerEntryNotFoundError on unknown entry id;
                 SchedulerEntryConflictError when the entry is
                 already cancelled (cannot dispatch a cancelled
                 entry).
    """
    row = repository.find_by_id(db_session=db_session, entry_id=entry_id)
    if row is None:
        err_lines = ["Scheduler entry not found."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerEntryNotFoundError(err_msg) from None

    if row.state == SchedulerEntryState.DISPATCHED:
        rtnval = _to_view(row=row)
        return rtnval
    if row.state == SchedulerEntryState.CANCELLED:
        err_lines = ["Cannot dispatch a cancelled entry."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerEntryConflictError(err_msg) from None

    now = utc_now()
    row.state = SchedulerEntryState.DISPATCHED
    row.dispatched_at = now
    row.version = row.version + 1
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SchedulerEventTopics.DISPATCHED,
            payload={
                "entry_id": str(row.entry_id),
                "reservation_id": str(row.reservation_id),
                "pool_id": str(row.pool_id),
                "dispatched_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_entry(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> SchedulerEntryView:
    """
        Read a single entry.

        :raises: SchedulerEntryNotFoundError on miss.
    """
    row = repository.find_by_id(db_session=db_session, entry_id=entry_id)
    if row is None:
        err_lines = ["Scheduler entry not found."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerEntryNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_queued_for_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> List[SchedulerEntryView]:
    """
        Return every queued entry on ``pool_id`` ordered by
        ``enqueued_at``.
    """
    rows = repository.list_queued_for_pool(
        db_session=db_session, pool_id=pool_id,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def _validate_aspects(*, aspects: SchedulerAspects) -> None:
    """
        Reject aspect bundles that violate the M1 invariants.
        ``priority`` must be in ``[0, 100]``;
        ``fair_share_weight`` must be in ``(0, 10]``;
        ``algorithm`` must be a non-empty string. ``deadline_at``
        validation against ``max_reservation_ttl_seconds`` lands
        in M2 once the ops-config feature exists.
    """
    if aspects.algorithm is None or len(aspects.algorithm) == 0:
        err_lines = ["Aspects.algorithm must be a non-empty string."]
        err_lines.append("VALUE: {!r}".format(aspects.algorithm))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerAspectsInvalidError(err_msg) from None

    if aspects.priority < PRIORITY_MIN or aspects.priority > PRIORITY_MAX:
        err_lines = ["Aspects.priority must be in [{}, {}].".format(
            PRIORITY_MIN, PRIORITY_MAX,
        )]
        err_lines.append("VALUE: {}".format(aspects.priority))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerAspectsInvalidError(err_msg) from None

    if aspects.fair_share_weight <= FAIR_SHARE_WEIGHT_MIN_EXCLUSIVE:
        err_lines = ["Aspects.fair_share_weight must be > 0."]
        err_lines.append("VALUE: {}".format(aspects.fair_share_weight))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerAspectsInvalidError(err_msg) from None
    if aspects.fair_share_weight > FAIR_SHARE_WEIGHT_MAX:
        err_lines = ["Aspects.fair_share_weight must be <= {}.".format(
            FAIR_SHARE_WEIGHT_MAX,
        )]
        err_lines.append("VALUE: {}".format(aspects.fair_share_weight))
        err_msg = os.linesep.join(err_lines)
        raise SchedulerAspectsInvalidError(err_msg) from None
    return


def _to_view(*, row: SchedulerEntry) -> SchedulerEntryView:
    rtnval = SchedulerEntryView(
        entry_id=str(row.entry_id),
        reservation_id=str(row.reservation_id),
        pool_id=str(row.pool_id),
        project_id=str(row.project_id),
        algorithm=row.algorithm,
        priority=row.priority,
        fair_share_key=row.fair_share_key,
        fair_share_weight=row.fair_share_weight,
        deadline_at=row.deadline_at,
        enqueued_at=row.enqueued_at,
        promoted_at=row.promoted_at,
        dispatched_at=row.dispatched_at,
        cancelled_at=row.cancelled_at,
        state=row.state,
    )
    return rtnval
