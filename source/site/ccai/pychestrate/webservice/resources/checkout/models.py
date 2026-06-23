"""
.. module:: resources.checkout.models
    :synopsis: SQLAlchemy model + enums for resource reservations.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ReservationMode(str, enum.Enum):
    """
        Sharing mode of a reservation.
    """
    EXCLUSIVE = "exclusive"
    SHARED = "shared"


class ReservationState(str, enum.Enum):
    """
        Lifecycle of a reservation row.
    """
    PENDING = "pending"
    GRANTED = "granted"
    RELEASED = "released"
    REJECTED = "rejected"
    FORCED_RELEASED = "forced_released"


RESERVATION_MODE_ENUM = "resources_reservation_mode"
RESERVATION_STATE_ENUM = "resources_reservation_state"


class Reservation(PychestratePhase1Base, SerializableModel):
    """
        Reservation row tying a project + actor + resource +
        state. M1 supports single-resource targets; pool-target
        reservations land in M2.
    """

    __tablename__ = "resources_reservation"

    reservation_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    resource_id = Column(UUIDType(binary=False), nullable=False)
    requested_by = Column(UUIDType(binary=False), nullable=True)
    mode = Column(
        Enum(ReservationMode, name=RESERVATION_MODE_ENUM),
        nullable=False,
        default=ReservationMode.EXCLUSIVE,
    )
    state = Column(
        Enum(ReservationState, name=RESERVATION_STATE_ENUM),
        nullable=False,
        default=ReservationState.PENDING,
    )
    note = Column(String(512), nullable=False, default="")
    requested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_resources_reservation_resource_state", "resource_id", "state"),
        Index("ix_resources_reservation_project", "project_id"),
        Index("ix_resources_reservation_requested_by", "requested_by"),
    )
