"""
.. module:: resources.lease.repository
    :synopsis: CRUD helpers for lease rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.resources.lease.models import (
    Lease,
    LeaseState,
)


def insert_lease(
        *,
        db_session: DbSession,
        reservation_id: str,
        project_id: str,
        resource_id: str,
        lease_kind: str,
        ttl_seconds: int,
        attached_at: datetime,
        expires_at: datetime
    ) -> Lease:
    """
        Insert a fresh lease row in ACTIVE.
    """
    row = Lease(
        lease_id=new_uuid(),
        reservation_id=reservation_id,
        project_id=project_id,
        resource_id=resource_id,
        lease_kind=lease_kind,
        ttl_seconds=ttl_seconds,
        state=LeaseState.ACTIVE,
        attached_at=attached_at,
        expires_at=expires_at,
        last_heartbeat_at=attached_at,
        closed_at=None,
        close_reason=None,
        heartbeat_count=0,
        version=1,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        lease_id: str
    ) -> Optional[Lease]:
    rtnval = (
        db_session.query(Lease)
        .filter(Lease.lease_id == lease_id)
        .first()
    )
    return rtnval


def find_by_reservation(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> Optional[Lease]:
    rtnval = (
        db_session.query(Lease)
        .filter(Lease.reservation_id == reservation_id)
        .first()
    )
    return rtnval


def list_active_expired_before(
        *,
        db_session: DbSession,
        when: datetime
    ) -> List[Lease]:
    """
        Sweeper input — every active lease whose
        ``expires_at <= when``.
    """
    rows = (
        db_session.query(Lease)
        .filter(Lease.state == LeaseState.ACTIVE)
        .filter(Lease.expires_at <= when)
        .order_by(Lease.expires_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_active_for_resource(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> List[Lease]:
    rows = (
        db_session.query(Lease)
        .filter(Lease.resource_id == resource_id)
        .filter(Lease.state == LeaseState.ACTIVE)
        .order_by(Lease.attached_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
