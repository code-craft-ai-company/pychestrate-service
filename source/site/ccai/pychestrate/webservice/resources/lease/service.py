"""
.. module:: resources.lease.service
    :synopsis: Lease facade — attach / heartbeat / release / sweep.

M1 hard-wires a fixed-TTL renewal policy: every successful
heartbeat resets ``expires_at = now + ttl_seconds``. The
:func:`sweep_expired` helper is the M1 stand-in for the M2
background sweeper — operators / tests call it directly with a
wall-clock timestamp; M2 ties it to a tick scheduler running
``min(ttl)/4`` cadence.

Per :func:`sweep_expired`, expiry closes the lease but does NOT
release the underlying reservation; the caller is responsible
for invoking :func:`resources.checkout.service.release` with
``forced=True`` after seeing ``entity.lease.expired``. The M2
release_reason wiring lands once the checkout module grows a
release_reason field.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.lease import repository
from ccai.pychestrate.webservice.resources.lease.errors import (
    LeaseAspectsInvalidError,
    LeaseNotFoundError,
    LeaseStateError,
)
from ccai.pychestrate.webservice.resources.lease.events import (
    LeaseEventTopics,
)
from ccai.pychestrate.webservice.resources.lease.models import (
    Lease,
    LeaseState,
)


DEFAULT_LEASE_KIND: str = "fixed"
DEFAULT_TTL_SECONDS: int = 60
TTL_MIN_SECONDS: int = 10
TTL_MAX_SECONDS: int = 3600


@dataclass(frozen=True)
class LeaseAspects:
    """
        Caller-tunable lease knobs.

        :param lease_kind: M2 wires this through the
                           ``lease_renewal_policy`` registry. M1
                           accepts any non-empty string and
                           records it for M2 replay.
        :param ttl_seconds: Time-to-live in seconds. Clamped to
                            :data:`TTL_MIN_SECONDS` /
                            :data:`TTL_MAX_SECONDS` at attach
                            time. Out-of-range values raise
                            :class:`LeaseAspectsInvalidError`.
    """
    lease_kind: str = DEFAULT_LEASE_KIND
    ttl_seconds: int = DEFAULT_TTL_SECONDS


@dataclass(frozen=True)
class LeaseView:
    """
        Caller-facing read-model.
    """
    lease_id: str
    reservation_id: str
    project_id: str
    resource_id: str
    lease_kind: str
    ttl_seconds: int
    state: LeaseState
    attached_at: datetime
    expires_at: datetime
    last_heartbeat_at: datetime
    closed_at: Optional[datetime]
    close_reason: Optional[str]
    heartbeat_count: int


def attach_lease(
        *,
        db_session: DbSession,
        reservation_id: str,
        project_id: str,
        resource_id: str,
        aspects: Optional[LeaseAspects] = None
    ) -> LeaseView:
    """
        Attach a lease to a granted reservation. Idempotent on a
        reservation that already has an active lease — the
        existing view is returned. A reservation that already
        carries a closed lease (expired or released) raises
        :class:`LeaseStateError` so callers cannot reattach.

        :raises: LeaseAspectsInvalidError, LeaseStateError.
    """
    effective = aspects or LeaseAspects()
    _validate_aspects(aspects=effective)

    existing = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if existing is not None:
        if existing.state == LeaseState.ACTIVE:
            rtnval = _to_view(row=existing)
            return rtnval
        err_lines = ["Reservation already has a closed lease."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_lines.append("LEASE_ID: {}".format(existing.lease_id))
        err_lines.append("STATE: {}".format(existing.state.value))
        err_msg = os.linesep.join(err_lines)
        raise LeaseStateError(err_msg) from None

    now = utc_now()
    expires_at = now + timedelta(seconds=effective.ttl_seconds)
    row = repository.insert_lease(
        db_session=db_session,
        reservation_id=reservation_id,
        project_id=project_id,
        resource_id=resource_id,
        lease_kind=effective.lease_kind,
        ttl_seconds=effective.ttl_seconds,
        attached_at=now,
        expires_at=expires_at,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=LeaseEventTopics.ATTACHED,
            payload={
                "lease_id": str(row.lease_id),
                "reservation_id": reservation_id,
                "project_id": project_id,
                "resource_id": resource_id,
                "lease_kind": effective.lease_kind,
                "ttl_seconds": effective.ttl_seconds,
                "expires_at": expires_at.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def heartbeat(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> LeaseView:
    """
        Renew a lease. Bumps ``expires_at = now + ttl_seconds``,
        ``last_heartbeat_at``, and ``heartbeat_count``. Emits
        :data:`LeaseEventTopics.RENEWED`.

        :raises: LeaseNotFoundError, LeaseStateError.
    """
    row = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["No lease for reservation."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise LeaseNotFoundError(err_msg) from None

    if row.state != LeaseState.ACTIVE:
        err_lines = ["Cannot heartbeat a closed lease."]
        err_lines.append("LEASE_ID: {}".format(row.lease_id))
        err_lines.append("STATE: {}".format(row.state.value))
        err_msg = os.linesep.join(err_lines)
        raise LeaseStateError(err_msg) from None

    now = utc_now()
    row.last_heartbeat_at = now
    row.expires_at = now + timedelta(seconds=row.ttl_seconds)
    row.heartbeat_count = row.heartbeat_count + 1
    row.version = row.version + 1
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=LeaseEventTopics.RENEWED,
            payload={
                "lease_id": str(row.lease_id),
                "reservation_id": str(row.reservation_id),
                "expires_at": row.expires_at.isoformat(),
                "heartbeat_count": row.heartbeat_count,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def release_lease(
        *,
        db_session: DbSession,
        reservation_id: str,
        reason: str = "released"
    ) -> LeaseView:
    """
        Close a lease in lockstep with the reservation release.
        Idempotent on already-closed leases.

        :raises: LeaseNotFoundError.
    """
    row = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["No lease for reservation."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise LeaseNotFoundError(err_msg) from None

    if row.state != LeaseState.ACTIVE:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = LeaseState.RELEASED
    row.closed_at = now
    row.close_reason = reason
    row.version = row.version + 1
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=LeaseEventTopics.RELEASED,
            payload={
                "lease_id": str(row.lease_id),
                "reservation_id": str(row.reservation_id),
                "resource_id": str(row.resource_id),
                "reason": reason,
                "closed_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def sweep_expired(
        *,
        db_session: DbSession,
        when: Optional[datetime] = None
    ) -> List[LeaseView]:
    """
        Close every ACTIVE lease whose ``expires_at <= when``.
        Each closed lease emits :data:`LeaseEventTopics.EXPIRED`
        with ``reason="lease_lost"``. Returns the closed views in
        ``expires_at`` order — useful for tests and for the M2
        sweeper to forward to the checkout layer for forced
        release.

        :param when: Wall-clock timestamp to sweep against;
                     defaults to :func:`utc_now`. Tests pass an
                     explicit moment to make assertions
                     deterministic.
    """
    cutoff = when if when is not None else utc_now()
    rows = repository.list_active_expired_before(
        db_session=db_session, when=cutoff,
    )
    closed_views: List[LeaseView] = []
    for row in rows:
        row.state = LeaseState.EXPIRED
        row.closed_at = cutoff
        row.close_reason = "lease_lost"
        row.version = row.version + 1
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=LeaseEventTopics.EXPIRED,
                payload={
                    "lease_id": str(row.lease_id),
                    "reservation_id": str(row.reservation_id),
                    "resource_id": str(row.resource_id),
                    "expires_at": row.expires_at.isoformat(),
                    "closed_at": cutoff.isoformat(),
                    "reason": "lease_lost",
                },
                source_event_id=new_uuid(),
            ),
        )
        closed_views.append(_to_view(row=row))
    db_session.commit()
    return closed_views


def get_lease(
        *,
        db_session: DbSession,
        lease_id: str
    ) -> LeaseView:
    """
        Read a lease by id.

        :raises: LeaseNotFoundError on miss.
    """
    row = repository.find_by_id(db_session=db_session, lease_id=lease_id)
    if row is None:
        err_lines = ["Lease not found."]
        err_lines.append("LEASE_ID: {}".format(lease_id))
        err_msg = os.linesep.join(err_lines)
        raise LeaseNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def get_lease_for_reservation(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> LeaseView:
    """
        Read the (single) lease attached to ``reservation_id``.

        :raises: LeaseNotFoundError on miss.
    """
    row = repository.find_by_reservation(
        db_session=db_session, reservation_id=reservation_id,
    )
    if row is None:
        err_lines = ["No lease for reservation."]
        err_lines.append("RESERVATION_ID: {}".format(reservation_id))
        err_msg = os.linesep.join(err_lines)
        raise LeaseNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def _validate_aspects(*, aspects: LeaseAspects) -> None:
    """
        Reject aspect bundles that violate the M1 invariants.
    """
    if aspects.lease_kind is None or len(aspects.lease_kind) == 0:
        err_lines = ["Aspects.lease_kind must be a non-empty string."]
        err_lines.append("VALUE: {!r}".format(aspects.lease_kind))
        err_msg = os.linesep.join(err_lines)
        raise LeaseAspectsInvalidError(err_msg) from None

    if aspects.ttl_seconds < TTL_MIN_SECONDS:
        err_lines = ["Aspects.ttl_seconds must be >= {}.".format(TTL_MIN_SECONDS)]
        err_lines.append("VALUE: {}".format(aspects.ttl_seconds))
        err_msg = os.linesep.join(err_lines)
        raise LeaseAspectsInvalidError(err_msg) from None
    if aspects.ttl_seconds > TTL_MAX_SECONDS:
        err_lines = ["Aspects.ttl_seconds must be <= {}.".format(TTL_MAX_SECONDS)]
        err_lines.append("VALUE: {}".format(aspects.ttl_seconds))
        err_msg = os.linesep.join(err_lines)
        raise LeaseAspectsInvalidError(err_msg) from None
    return


def _to_view(*, row: Lease) -> LeaseView:
    rtnval = LeaseView(
        lease_id=str(row.lease_id),
        reservation_id=str(row.reservation_id),
        project_id=str(row.project_id),
        resource_id=str(row.resource_id),
        lease_kind=row.lease_kind,
        ttl_seconds=row.ttl_seconds,
        state=row.state,
        attached_at=row.attached_at,
        expires_at=row.expires_at,
        last_heartbeat_at=row.last_heartbeat_at,
        closed_at=row.closed_at,
        close_reason=row.close_reason,
        heartbeat_count=row.heartbeat_count,
    )
    return rtnval
