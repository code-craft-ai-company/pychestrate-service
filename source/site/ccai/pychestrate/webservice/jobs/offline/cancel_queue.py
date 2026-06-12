"""
.. module:: jobs.offline.cancel_queue
    :synopsis: DeferredCancelQueue — queue cancels for offline pods.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.offline.models import (
    DeferredCancel,
    DeferredCancelStatus,
    PodLivenessTier,
)
from ccai.pychestrate.webservice.jobs.offline.pod_state import (
    PodOfflineStateService,
)


DEFAULT_QUEUE_TTL_SECONDS: int = 7 * 24 * 60 * 60


class DeferredCancelQueue:
    """
        Queues cancel-RPC requests against pods that are not
        currently HEALTHY, then replays them on reconnect.
    """

    def __init__(
            self,
            *,
            pod_state: PodOfflineStateService,
            queue_ttl_seconds: int = DEFAULT_QUEUE_TTL_SECONDS
        ) -> None:
        self._pod_state: PodOfflineStateService = pod_state
        self._queue_ttl_seconds: int = queue_ttl_seconds
        return

    def queue_if_offline(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            client_id: str,
            pod_id: str,
            cancel_request_id: str,
            reason: str
        ) -> Optional[DeferredCancel]:
        """
            If the pod is HEALTHY, return ``None`` so the caller
            (the cancel dispatcher) proceeds with a live transmit.
            Otherwise, queue a deferred row and return it.
        """
        tier = self._pod_state.evaluate_tier(
            db_session=db_session, pod_id=pod_id,
        )
        if tier == PodLivenessTier.HEALTHY:
            return None

        now = utc_now()
        row = DeferredCancel(
            deferred_id=new_uuid(),
            run_id=run_id,
            project_id=project_id,
            client_id=client_id,
            pod_id=pod_id,
            cancel_request_id=cancel_request_id,
            reason=reason,
            status=DeferredCancelStatus.QUEUED,
            queued_at=now,
            expires_at=now + timedelta(seconds=self._queue_ttl_seconds),
        )
        db_session.add(row)
        db_session.flush()
        db_session.commit()
        return row

    def list_queued_for_pod(
            self,
            *,
            db_session: DbSession,
            pod_id: str
        ) -> List[DeferredCancel]:
        """
            Return every queued deferred cancel for ``pod_id``
            ordered by ``queued_at``. The reconnect handler
            iterates this list to deliver pending cancels.
        """
        rows = (
            db_session.query(DeferredCancel)
            .filter(DeferredCancel.pod_id == pod_id)
            .filter(DeferredCancel.status == DeferredCancelStatus.QUEUED)
            .order_by(DeferredCancel.queued_at.asc())
            .all()
        )
        rtnval = list(rows)
        return rtnval

    def mark_delivered(
            self,
            *,
            db_session: DbSession,
            row: DeferredCancel
        ) -> None:
        """
            Flip a queued row to ``DELIVERED`` after the live
            transmit succeeds.
        """
        row.status = DeferredCancelStatus.DELIVERED
        row.delivered_at = utc_now()
        db_session.flush()
        db_session.commit()
        return

    def mark_expired_overdue(
            self,
            *,
            db_session: DbSession,
            now: Optional[datetime] = None
        ) -> int:
        """
            Sweep queued rows whose ``expires_at`` has passed and
            flip them to ``EXPIRED``. Returns the number flipped.
        """
        when = now
        if when is None:
            when = utc_now()
        rows = (
            db_session.query(DeferredCancel)
            .filter(DeferredCancel.status == DeferredCancelStatus.QUEUED)
            .filter(DeferredCancel.expires_at <= when)
            .all()
        )
        for row in rows:
            row.status = DeferredCancelStatus.EXPIRED
            row.failure_reason = "queue ttl expired"
        if len(rows) > 0:
            db_session.flush()
            db_session.commit()
        rtnval = len(rows)
        return rtnval
