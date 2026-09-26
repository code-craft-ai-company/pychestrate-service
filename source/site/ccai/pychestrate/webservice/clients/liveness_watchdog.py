"""
.. module:: clients.liveness_watchdog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Derive each client's liveness from how long ago it last
               heartbeated.

.. moduleauthor:: Code Craft AI LLC

Liveness used to be decorative (RES-36): a heartbeat set a client
``ALIVE``, but nothing ever moved it anywhere else, so a pod that
stopped 50 minutes ago -- or had never heartbeated at all -- still
showed ``ALIVE``, and a trigger against it was accepted with no hint it
would sit waiting (E2E-16).

:func:`scan_client_liveness` runs on the reconciler's periodic scan. For
every ACTIVE client it measures the silence since ``last_seen`` (or
since enrollment, for a client that never heartbeated) and moves it to
``DEGRADED`` after :data:`DEFAULT_DEGRADED_AFTER_SECONDS` and ``LOST``
after :data:`DEFAULT_LOST_AFTER_SECONDS`. A heartbeat moves it back to
``ALIVE`` (:func:`registry.service.record_heartbeat`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.clients.enums import ClientStatus, LivenessState
from ccai.pychestrate.webservice.clients.models import Client
from ccai.pychestrate.webservice.clients.registry.service import set_liveness_state


#: Silence after which a client is DEGRADED ("stale"): three missed
#: beats at the pod's default 30 s heartbeat interval.
DEFAULT_DEGRADED_AFTER_SECONDS: int = 90

#: Silence after which a client is LOST: ten missed default beats.
DEFAULT_LOST_AFTER_SECONDS: int = 300


@dataclass(frozen=True)
class LivenessChange:
    """
        One liveness transition the watchdog applied.

        :param client_id: Client UUID.
        :param previous_state: State before the scan.
        :param new_state: State after the scan.
        :param silent_seconds: Seconds since the client was last heard from.
    """
    client_id: str
    previous_state: LivenessState
    new_state: LivenessState
    silent_seconds: float


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def derive_liveness(
        *,
        last_seen: Optional[datetime],
        enrolled_at: Optional[datetime],
        now: datetime,
        degraded_after_seconds: float = DEFAULT_DEGRADED_AFTER_SECONDS,
        lost_after_seconds: float = DEFAULT_LOST_AFTER_SECONDS
    ) -> LivenessState:
    """
        The liveness a client's silence implies.

        :param last_seen: Last heartbeat, or None when it never heartbeated.
        :param enrolled_at: Enrollment time; the silence of a client that
                            never heartbeated counts from here.
        :param now: Evaluation time.
        :param degraded_after_seconds: Silence that makes it DEGRADED.
        :param lost_after_seconds: Silence that makes it LOST.

        :returns: The derived :class:`LivenessState`.
    """
    reference = _as_utc(last_seen)
    if reference is None:
        reference = _as_utc(enrolled_at)
    if reference is None:
        return LivenessState.LOST

    silent_seconds = (_as_utc(now) - reference).total_seconds()
    rtnval = LivenessState.ALIVE
    if silent_seconds >= lost_after_seconds:
        rtnval = LivenessState.LOST
    elif silent_seconds >= degraded_after_seconds:
        rtnval = LivenessState.DEGRADED
    return rtnval


def scan_client_liveness(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None,
        degraded_after_seconds: float = DEFAULT_DEGRADED_AFTER_SECONDS,
        lost_after_seconds: float = DEFAULT_LOST_AFTER_SECONDS
    ) -> List[LivenessChange]:
    """
        Re-derive the liveness of every ACTIVE client and apply the
        changes (each publishes ``entity.client.liveness_changed``).
        Revoked and suspended clients are left alone: they are not
        expected to heartbeat.

        :param db_session: Active SQLAlchemy session.
        :param now: Evaluation time (tests); defaults to now.
        :param degraded_after_seconds: Silence that makes a client DEGRADED.
        :param lost_after_seconds: Silence that makes a client LOST.

        :returns: The transitions applied.
    """
    effective_now = now if now is not None else utc_now()
    rows = (
        db_session.query(Client)
        .filter(Client.status == ClientStatus.ACTIVE)
        .all()
    )

    changes: List[LivenessChange] = []
    for row in rows:
        desired = derive_liveness(
            last_seen=row.last_seen,
            enrolled_at=row.enrolled_at,
            now=effective_now,
            degraded_after_seconds=degraded_after_seconds,
            lost_after_seconds=lost_after_seconds,
        )
        if desired == row.liveness_state:
            continue
        previous = row.liveness_state
        reference = _as_utc(row.last_seen) or _as_utc(row.enrolled_at) or effective_now
        set_liveness_state(
            db_session=db_session, client_id=str(row.client_id),
            liveness_state=desired, now=effective_now,
        )
        changes.append(LivenessChange(
            client_id=str(row.client_id),
            previous_state=previous,
            new_state=desired,
            silent_seconds=(_as_utc(effective_now) - reference).total_seconds(),
        ))

    rtnval = changes
    return rtnval


def pod_availability_warning(
        *,
        db_session: DbSession,
        client_id: Optional[str],
        now: Optional[datetime] = None
    ) -> Optional[str]:
    """
        A warning for a trigger whose run went to a pod that is not
        currently heartbeating. The run is still queued -- it is
        delivered when the pod reconnects -- but the caller should know
        it will wait (E2E-16: a trigger against a stopped pod was
        accepted silently). Liveness is derived from ``last_seen`` here
        rather than read from the column, which the watchdog only
        refreshes every scan.

        :param db_session: Active SQLAlchemy session.
        :param client_id: The client the run was dispatched to.
        :param now: Evaluation time (tests).

        :returns: The warning text, or None when the pod is alive (or
                  the client is unknown).
    """
    if client_id is None:
        return None
    client = db_session.query(Client).filter(Client.client_id == str(client_id)).first()
    if client is None:
        return None

    effective_now = now if now is not None else utc_now()
    liveness = derive_liveness(last_seen=client.last_seen, enrolled_at=client.enrolled_at, now=effective_now)
    if liveness == LivenessState.ALIVE and client.last_seen is not None:
        return None

    if client.last_seen is None:
        rtnval = ("Pod {!r} has never checked in; the run is queued and starts once its "
                  "client connects.".format(client.pod_name))
    else:
        silent_minutes = int((_as_utc(effective_now) - _as_utc(client.last_seen)).total_seconds() // 60)
        rtnval = ("Pod {!r} was last heard from {} minute(s) ago; the run is queued and "
                  "starts when it reconnects.".format(client.pod_name, silent_minutes))
    return rtnval


__all__ = [
    "DEFAULT_DEGRADED_AFTER_SECONDS",
    "DEFAULT_LOST_AFTER_SECONDS",
    "LivenessChange",
    "derive_liveness",
    "pod_availability_warning",
    "scan_client_liveness",
]
