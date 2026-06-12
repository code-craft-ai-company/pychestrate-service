"""
.. module:: resources.checkout.repository
    :synopsis: CRUD helpers for reservation rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.resources.checkout.models import (
    Reservation,
    ReservationMode,
    ReservationState,
)


def insert_reservation(
        *,
        db_session: DbSession,
        project_id: str,
        resource_id: str,
        requested_by: Optional[str],
        mode: ReservationMode,
        note: str,
        requested_at: datetime
    ) -> Reservation:
    """
        Insert a fresh reservation row in PENDING.
    """
    row = Reservation(
        reservation_id=new_uuid(),
        project_id=project_id,
        resource_id=resource_id,
        requested_by=requested_by,
        mode=mode,
        state=ReservationState.PENDING,
        note=note,
        requested_at=requested_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_active_reservations(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> List[Reservation]:
    """
        Return GRANTED reservations against ``resource_id`` —
        the conflict evaluator's input set.
    """
    rows = (
        db_session.query(Reservation)
        .filter(Reservation.resource_id == resource_id)
        .filter(Reservation.state == ReservationState.GRANTED)
        .order_by(Reservation.requested_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_by_id(
        *,
        db_session: DbSession,
        reservation_id: str
    ) -> Optional[Reservation]:
    rtnval = (
        db_session.query(Reservation)
        .filter(Reservation.reservation_id == reservation_id)
        .first()
    )
    return rtnval


def list_for_resource(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> List[Reservation]:
    rows = (
        db_session.query(Reservation)
        .filter(Reservation.resource_id == resource_id)
        .order_by(Reservation.requested_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
