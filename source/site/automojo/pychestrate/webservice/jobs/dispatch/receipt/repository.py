"""
.. module:: jobs.dispatch.receipt.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for dispatch receipts.

.. moduleauthor:: Automation Mojo LLC

M1 implements idempotent insert via an explicit
"lookup-or-create" pattern because the legacy SQLite test harness
does not honor ``ON CONFLICT`` in the same shape across dialects.
The unique constraint on ``(client_id, client_local_run_id)``
still enforces the invariant at the database level in production.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.jobs.dispatch.receipt.models import (
    DispatchReceipt,
)


def find_by_local_key(
        *,
        db_session: DbSession,
        client_id: str,
        client_local_run_id: str
    ) -> Optional[DispatchReceipt]:
    """
        Fetch an existing row by ``(client_id, client_local_run_id)``
        without raising. Returns ``None`` when no row matches.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Client UUID.
        :param client_local_run_id: Client-assigned local id.

        :returns: Row or ``None``.
    """
    rtnval = (
        db_session.query(DispatchReceipt)
        .filter(DispatchReceipt.client_id == client_id)
        .filter(DispatchReceipt.client_local_run_id == client_local_run_id)
        .first()
    )
    return rtnval


def find_by_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[DispatchReceipt]:
    """
        Fetch the receipt bound to a run id. A run may have at
        most one receipt; a second distinct one is rejected at
        the service layer before this helper is called.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: Row or ``None``.
    """
    rtnval = (
        db_session.query(DispatchReceipt)
        .filter(DispatchReceipt.run_id == run_id)
        .first()
    )
    return rtnval


def insert_receipt(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        client_id: str,
        attempt_id: str,
        envelope_id: str,
        client_local_run_id: str,
        received_at: datetime,
        deadline_at: Optional[datetime],
        late_arrival: bool,
        launch_pid: Optional[int]
    ) -> DispatchReceipt:
    """
        Insert a fresh receipt row. Callers MUST ensure the
        ``(client_id, client_local_run_id)`` pair does not already
        exist; :func:`service.record` enforces idempotency.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param client_id: Client UUID.
        :param attempt_id: Linked attempt UUID.
        :param envelope_id: Envelope UUID the receipt acknowledges.
        :param client_local_run_id: Client-assigned local id.
        :param received_at: Commit timestamp.
        :param deadline_at: Deadline expected by the dispatcher.
        :param late_arrival: Whether the receipt missed the
                             deadline.
        :param launch_pid: Client-reported process id, nullable.

        :returns: Persisted row.
    """
    row = DispatchReceipt(
        receipt_id=new_uuid(),
        run_id=run_id,
        project_id=project_id,
        client_id=client_id,
        attempt_id=attempt_id,
        envelope_id=envelope_id,
        client_local_run_id=client_local_run_id,
        received_at=received_at,
        deadline_at=deadline_at,
        late_arrival=late_arrival,
        launch_pid=launch_pid,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_receipts(
        *,
        db_session: DbSession,
        project_id: Optional[str] = None
    ) -> List[DispatchReceipt]:
    """
        Return every receipt, optionally filtered by project.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Optional project UUID filter.

        :returns: List of receipts ordered by ``received_at``.
    """
    query = db_session.query(DispatchReceipt)
    if project_id is not None:
        query = query.filter(DispatchReceipt.project_id == project_id)
    rows = query.order_by(DispatchReceipt.received_at.asc()).all()
    rtnval = list(rows)
    return rtnval
