"""
.. module:: resources.checkout.service
    :synopsis: Reservation facade — reserve / release / get / list.

``reserve`` is the linchpin of Layer-4 contention: it locks the
target resource row, snapshots active reservations, runs every
registered conflict rule via the evaluator, and either commits a
``GRANTED`` row or persists a ``REJECTED`` row with the rule's
reason. Releases flip ``GRANTED → RELEASED`` (or ``REJECTED →
RELEASED`` for forced cleanups) and emit
``entity.reservation.released``.
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
from ccai.pychestrate.webservice.resources.checkout import repository
from ccai.pychestrate.webservice.resources.checkout.errors import (
    ReservationConflictError,
    ReservationNotFoundError,
    ReservationStateError,
)
from ccai.pychestrate.webservice.resources.checkout.events import (
    ReservationEventTopics,
)
from ccai.pychestrate.webservice.resources.checkout.models import (
    Reservation,
    ReservationMode,
    ReservationState,
)
from ccai.pychestrate.webservice.resources.conflict.evaluator import (
    ActiveReservationSnapshot,
    CandidateReservation,
    evaluate,
)


@dataclass(frozen=True)
class ReservationAspects:
    """
        Caller-tunable knobs. ``note`` is persisted on the row.
        Future fields land in M2 (``priority``,
        ``release_on_disconnect``, etc).
    """
    note: str = ""


@dataclass(frozen=True)
class ReservationView:
    """
        Read-model returned to callers.
    """
    reservation_id: str
    project_id: str
    resource_id: str
    requested_by: Optional[str]
    mode: ReservationMode
    state: ReservationState
    note: str
    requested_at: datetime
    granted_at: Optional[datetime]
    released_at: Optional[datetime]
    rejection_reason: Optional[str]


def reserve(
        *,
        db_session: DbSession,
        project_id: str,
        resource_id: str,
        requested_by: Optional[str],
        mode: ReservationMode,
        aspects: Optional[ReservationAspects] = None
    ) -> ReservationView:
    """
        Open a reservation. Runs the conflict evaluator before
        committing — a vetoed reserve persists a REJECTED row
        and raises :class:`ReservationConflictError`. A successful
        reserve commits a GRANTED row and emits both
        ``entity.reservation.created`` and
        ``entity.reservation.granted``.

        :raises: ReservationConflictError on rule veto.
    """
    effective_aspects = aspects or ReservationAspects()
    now = utc_now()

    active = repository.find_active_reservations(
        db_session=db_session, resource_id=resource_id,
    )
    candidate = CandidateReservation(
        project_id=project_id,
        resource_id=resource_id,
        mode=mode.value,
        requested_by=requested_by,
    )
    active_snapshots = [
        ActiveReservationSnapshot(
            reservation_id=str(r.reservation_id),
            project_id=str(r.project_id),
            resource_id=str(r.resource_id),
            mode=r.mode.value,
            requested_by=str(r.requested_by) if r.requested_by is not None else None,
        )
        for r in active
    ]
    evaluation = evaluate(
        candidate=candidate, active_reservations=active_snapshots,
    )

    row = repository.insert_reservation(
        db_session=db_session,
        project_id=project_id,
        resource_id=resource_id,
        requested_by=requested_by,
        mode=mode,
        note=effective_aspects.note,
        requested_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ReservationEventTopics.CREATED,
            payload={
                "reservation_id": str(row.reservation_id),
                "project_id": project_id,
                "resource_id": resource_id,
                "mode": mode.value,
                "requested_by": requested_by,
            },
            source_event_id=new_uuid(),
        ),
    )

    if evaluation.accepted is False:
        row.state = ReservationState.REJECTED
        decisions_text = "; ".join(
            "{}: {}".format(d.rule_name, d.reason)
            for d in evaluation.decisions if d.accepted is False
        )
        row.rejection_reason = decisions_text or "rejected"
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ReservationEventTopics.CONFLICT_REJECTED,
                payload={
                    "reservation_id": str(row.reservation_id),
                    "project_id": project_id,
                    "resource_id": resource_id,
                    "vetoed_by": evaluation.vetoed_by,
                    "reason": row.rejection_reason,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        err_lines = ["Reservation rejected by conflict rule."]
        err_lines.append("RESERVATION_ID: {}".format(row.reservation_id))
        err_lines.append("VETOED_BY: {}".format(evaluation.vetoed_by))
        err_lines.append("REASON: {}".format(row.rejection_reason))
        err_msg = os.linesep.join(err_lines)
        raise ReservationConflictError(err_msg) from None

    row.state = ReservationState.GRANTED
    row.granted_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ReservationEventTopics.GRANTED,
            payload={
                "reservation_id": str(row.reservation_id),
                "project_id": project_id,
                "resource_id": resource_id,
                "mode": mode.value,
                "granted_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def release(
        *,
        db_session: DbSession,
        reservation_id: str,
        forced: bool = False
    ) -> ReservationView:
    """
        Release a GRANTED reservation. Idempotent on already-
        released rows (returns the existing view). ``forced=True``
        emits ``entity.reservation.forced_released`` instead of
        the standard release event.
    """
    row = repository.find_by_id(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["Reservation not found."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise ReservationNotFoundError(err_msg) from None

    if row.state in (ReservationState.RELEASED, ReservationState.FORCED_RELEASED):
        rtnval = _to_view(row=row)
        return rtnval
    if row.state == ReservationState.REJECTED:
        # Rejected reservations are terminal too — no release
        # needed.
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = (
        ReservationState.FORCED_RELEASED if forced is True
        else ReservationState.RELEASED
    )
    row.released_at = now
    db_session.flush()

    topic = (
        ReservationEventTopics.FORCED_RELEASED if forced is True
        else ReservationEventTopics.RELEASED
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=topic,
            payload={
                "reservation_id": str(row.reservation_id),
                "project_id": str(row.project_id),
                "resource_id": str(row.resource_id),
                "released_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_reservation(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> ReservationView:
    row = repository.find_by_id(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["Reservation not found."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise ReservationNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_reservations_for_resource(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> List[ReservationView]:
    rows = repository.list_for_resource(
        db_session=db_session, resource_id=resource_id,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def _to_view(*, row: Reservation) -> ReservationView:
    rtnval = ReservationView(
        reservation_id=str(row.reservation_id),
        project_id=str(row.project_id),
        resource_id=str(row.resource_id),
        requested_by=str(row.requested_by) if row.requested_by is not None else None,
        mode=row.mode,
        state=row.state,
        note=row.note,
        requested_at=row.requested_at,
        granted_at=row.granted_at,
        released_at=row.released_at,
        rejection_reason=row.rejection_reason,
    )
    return rtnval
