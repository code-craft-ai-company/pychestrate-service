"""
.. module:: jobs.offline.pod_state
    :synopsis: PodOfflineStateService — drop / reconnect bookkeeping.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.jobs.offline.models import (
    PodLivenessTier,
    PodOfflineState,
)


DEFAULT_DEGRADED_AFTER_SECONDS: int = 30
DEFAULT_OFFLINE_AFTER_SECONDS: int = 300


class PodOfflineStateService:
    """
        Tracks the per-pod liveness tier driven by client
        session-dropped / reconnected events.
    """

    def __init__(
            self,
            *,
            degrade_after_seconds: int = DEFAULT_DEGRADED_AFTER_SECONDS,
            offline_after_seconds: int = DEFAULT_OFFLINE_AFTER_SECONDS
        ) -> None:
        self._degrade_after_seconds: int = degrade_after_seconds
        self._offline_after_seconds: int = offline_after_seconds
        return

    def degrade_after_seconds(self) -> int:
        rtnval = self._degrade_after_seconds
        return rtnval

    def offline_after_seconds(self) -> int:
        rtnval = self._offline_after_seconds
        return rtnval

    def observe_session_dropped(
            self,
            *,
            db_session: DbSession,
            pod_id: str,
            project_id: str,
            client_id: str,
            dropped_at: Optional[datetime] = None
        ) -> PodOfflineState:
        """
            Mark a pod as DEGRADED on session drop. The actual
            transition to OFFLINE happens via :meth:`evaluate_tier`
            when enough time has elapsed.
        """
        when = dropped_at
        if when is None:
            when = utc_now()
        row = self._upsert(
            db_session=db_session,
            pod_id=pod_id,
            project_id=project_id,
            client_id=client_id,
        )
        row.last_session_dropped_at = when
        row.tier = PodLivenessTier.DEGRADED
        row.updated_at = when
        db_session.flush()
        db_session.commit()
        return row

    def observe_reconnected(
            self,
            *,
            db_session: DbSession,
            pod_id: str,
            project_id: str,
            client_id: str,
            reconnected_at: Optional[datetime] = None
        ) -> PodOfflineState:
        """
            Mark a pod HEALTHY on reconnect.
        """
        when = reconnected_at
        if when is None:
            when = utc_now()
        row = self._upsert(
            db_session=db_session,
            pod_id=pod_id,
            project_id=project_id,
            client_id=client_id,
        )
        row.last_reconnected_at = when
        row.tier = PodLivenessTier.HEALTHY
        row.updated_at = when
        db_session.flush()
        db_session.commit()
        return row

    def evaluate_tier(
            self,
            *,
            db_session: DbSession,
            pod_id: str,
            now: Optional[datetime] = None
        ) -> PodLivenessTier:
        """
            Compute the current liveness tier for a pod based on
            elapsed time since its last session drop. Idempotent —
            callers invoke this on a tick or on demand.
        """
        when = now
        if when is None:
            when = utc_now()
        row = (
            db_session.query(PodOfflineState)
            .filter(PodOfflineState.pod_id == pod_id)
            .first()
        )
        if row is None:
            return PodLivenessTier.HEALTHY
        if row.tier == PodLivenessTier.HEALTHY:
            return PodLivenessTier.HEALTHY
        dropped = row.last_session_dropped_at
        if dropped is None:
            return row.tier
        # SQLite strips tz-info on round-trip; coerce both sides
        # to UTC-aware before subtracting so the test path works
        # identically against SQLite and Postgres.
        if dropped.tzinfo is None:
            dropped = dropped.replace(tzinfo=timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        elapsed = (when - dropped).total_seconds()
        if elapsed >= self._offline_after_seconds:
            row.tier = PodLivenessTier.OFFLINE
            row.updated_at = when
            db_session.flush()
            db_session.commit()
            return PodLivenessTier.OFFLINE
        if elapsed >= self._degrade_after_seconds:
            return PodLivenessTier.DEGRADED
        # Below the degrade threshold but the row is already in
        # DEGRADED (or higher) — once observed dropped the pod
        # stays at minimum DEGRADED until reconnect. Returning
        # HEALTHY here would incorrectly re-eligibilize the pod
        # for dispatch.
        return row.tier

    def evaluate_all_pods(
            self,
            *,
            db_session: DbSession,
            now: Optional[datetime] = None
        ) -> List[str]:
        """
            Walk every tracked pod, re-evaluating its liveness
            tier. Used by the phase-5 periodic offline-tolerance
            tick so DEGRADED pods become OFFLINE after their
            offline-grace window elapses, even when no further
            events arrive.

            :param db_session: Active SQLAlchemy session.
            :param now: Optional override for the current time.

            :returns: List of pod ids whose tier was re-evaluated
                      (the row may or may not have transitioned).
        """
        rows = db_session.query(PodOfflineState).all()
        evaluated: List[str] = []
        for row in rows:
            pod_id = str(row.pod_id)
            self.evaluate_tier(
                db_session=db_session, pod_id=pod_id, now=now,
            )
            evaluated.append(pod_id)
        rtnval = evaluated
        return rtnval

    def is_eligible_for_dispatch(
            self,
            *,
            db_session: DbSession,
            pod_id: str
        ) -> bool:
        """
            Return ``True`` when the pod is HEALTHY (the dispatch
            eligibility filter consumes this when the pod-state
            service is wired in M2).
        """
        tier = self.evaluate_tier(db_session=db_session, pod_id=pod_id)
        rtnval = tier == PodLivenessTier.HEALTHY
        return rtnval

    def _upsert(
            self,
            *,
            db_session: DbSession,
            pod_id: str,
            project_id: str,
            client_id: str
        ) -> PodOfflineState:
        row = (
            db_session.query(PodOfflineState)
            .filter(PodOfflineState.pod_id == pod_id)
            .first()
        )
        if row is None:
            row = PodOfflineState(
                pod_id=pod_id,
                project_id=project_id,
                client_id=client_id,
                tier=PodLivenessTier.HEALTHY,
            )
            db_session.add(row)
            db_session.flush()
        return row
