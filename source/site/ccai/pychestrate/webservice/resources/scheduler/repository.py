"""
.. module:: resources.scheduler.repository
    :synopsis: CRUD helpers for scheduler entries.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.resources.scheduler.models import (
    SchedulerEntry,
    SchedulerEntryState,
)


def insert_entry(
        *,
        db_session: DbSession,
        reservation_id: str,
        pool_id: str,
        project_id: str,
        algorithm: str,
        priority: int,
        fair_share_key: Optional[str],
        fair_share_weight: float,
        deadline_at: Optional[datetime],
        enqueued_at: datetime
    ) -> SchedulerEntry:
    """
        Insert a fresh scheduler entry in QUEUED.
    """
    row = SchedulerEntry(
        entry_id=new_uuid(),
        reservation_id=reservation_id,
        pool_id=pool_id,
        project_id=project_id,
        algorithm=algorithm,
        priority=priority,
        fair_share_key=fair_share_key,
        fair_share_weight=fair_share_weight,
        deadline_at=deadline_at,
        enqueued_at=enqueued_at,
        state=SchedulerEntryState.QUEUED,
        version=1,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> Optional[SchedulerEntry]:
    rtnval = (
        db_session.query(SchedulerEntry)
        .filter(SchedulerEntry.entry_id == entry_id)
        .first()
    )
    return rtnval


def find_by_reservation(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> Optional[SchedulerEntry]:
    rtnval = (
        db_session.query(SchedulerEntry)
        .filter(SchedulerEntry.reservation_id == reservation_id)
        .first()
    )
    return rtnval


def find_next_queued_for_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> Optional[SchedulerEntry]:
    """
        FIFO over queued entries — promoted entries (those with a
        non-null ``promoted_at``) jump the head, otherwise rows
        sort by ``enqueued_at``.
    """
    rows = (
        db_session.query(SchedulerEntry)
        .filter(SchedulerEntry.pool_id == pool_id)
        .filter(SchedulerEntry.state == SchedulerEntryState.QUEUED)
        .order_by(
            SchedulerEntry.promoted_at.is_(None).asc(),
            SchedulerEntry.promoted_at.asc(),
            SchedulerEntry.enqueued_at.asc(),
        )
        .all()
    )
    if len(rows) == 0:
        return None
    rtnval = rows[0]
    return rtnval


def list_queued_for_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> List[SchedulerEntry]:
    rows = (
        db_session.query(SchedulerEntry)
        .filter(SchedulerEntry.pool_id == pool_id)
        .filter(SchedulerEntry.state == SchedulerEntryState.QUEUED)
        .order_by(SchedulerEntry.enqueued_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_for_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> List[SchedulerEntry]:
    rows = (
        db_session.query(SchedulerEntry)
        .filter(SchedulerEntry.pool_id == pool_id)
        .order_by(SchedulerEntry.enqueued_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
