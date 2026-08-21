"""
.. module:: jobs.cancel.repository
    :synopsis: CRUD helpers for cancel_request rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.jobs.cancel.models import (
    CancelRequest,
    CancelStatus,
)


def insert_request(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        client_id: str,
        requested_by: Optional[str],
        reason: str,
        requested_at: datetime
    ) -> CancelRequest:
    """
        Insert a fresh cancel-request row in PENDING.
    """
    row = CancelRequest(
        request_id=new_uuid(),
        run_id=run_id,
        project_id=project_id,
        client_id=client_id,
        requested_by=requested_by,
        reason=reason,
        status=CancelStatus.PENDING,
        requested_at=requested_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_open_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[CancelRequest]:
    """
        Return any open (PENDING / TRANSMITTED / QUEUED_OFFLINE)
        request for the run, or ``None``.
    """
    rtnval = (
        db_session.query(CancelRequest)
        .filter(CancelRequest.run_id == run_id)
        .filter(CancelRequest.status.in_(
            (CancelStatus.PENDING, CancelStatus.TRANSMITTED, CancelStatus.QUEUED_OFFLINE),
        ))
        .first()
    )
    return rtnval


def list_open_for_client(
        *,
        db_session: DbSession,
        client_id: str
    ) -> List[CancelRequest]:
    """
        Return every open (PENDING / TRANSMITTED / QUEUED_OFFLINE)
        cancel request targeting ``client_id``, oldest first.

        This is the read the pod-client heartbeat drain issues:
        the open rows ARE the pull queue for the
        :class:`jobs.cancel.heartbeattransport.HeartbeatCancelTransport`.
        A row stays open — and is therefore re-delivered on every
        heartbeat — until the client acknowledges it, which makes
        delivery at-least-once over a channel that can drop a
        response.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Target client UUID.

        :returns: List of open cancel requests (possibly empty).
    """
    rows = (
        db_session.query(CancelRequest)
        .filter(CancelRequest.client_id == client_id)
        .filter(CancelRequest.status.in_(
            (CancelStatus.PENDING, CancelStatus.TRANSMITTED, CancelStatus.QUEUED_OFFLINE),
        ))
        .order_by(CancelRequest.requested_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_open_for_run_and_client(
        *,
        db_session: DbSession,
        run_id: str,
        client_id: str
    ) -> Optional[CancelRequest]:
    """
        Return the open cancel request for a ``(run_id, client_id)``
        pair, or ``None``.

        The client-facing cancel-ack path uses this rather than
        :func:`get_request` so a pod can only ever close a cancel
        request that was actually addressed to it.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param client_id: Target client UUID.

        :returns: The open :class:`CancelRequest` or None.
    """
    rtnval = (
        db_session.query(CancelRequest)
        .filter(CancelRequest.run_id == run_id)
        .filter(CancelRequest.client_id == client_id)
        .filter(CancelRequest.status.in_(
            (CancelStatus.PENDING, CancelStatus.TRANSMITTED, CancelStatus.QUEUED_OFFLINE),
        ))
        .first()
    )
    return rtnval


def get_request(
        *,
        db_session: DbSession,
        request_id: str
    ) -> Optional[CancelRequest]:
    """
        Fetch a cancel request by id.
    """
    rtnval = (
        db_session.query(CancelRequest)
        .filter(CancelRequest.request_id == request_id)
        .first()
    )
    return rtnval


def list_requests_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[CancelRequest]:
    """
        Return every cancel request for ``run_id``.
    """
    rows = (
        db_session.query(CancelRequest)
        .filter(CancelRequest.run_id == run_id)
        .order_by(CancelRequest.requested_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
