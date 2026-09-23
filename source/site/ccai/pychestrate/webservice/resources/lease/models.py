"""
.. module:: resources.lease.models
    :synopsis: SQLAlchemy model + enum for lease rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    Enum,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class LeaseState(str, enum.Enum):
    """
        Lifecycle of a lease row.

        * ``ACTIVE`` — heartbeats keep this lease alive.
        * ``EXPIRED`` — sweeper closed the lease for missed
          heartbeats; reservation gets released with
          ``release_reason=lease_lost``.
        * ``RELEASED`` — reservation released through the normal
          release path; lease closed alongside.
    """
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


LEASE_STATE_ENUM = "resources_lease_state"


class Lease(PychestratePhase1Base, SerializableModel):
    """
        Lease row backing a granted reservation. M1 hard-wires a
        fixed-TTL renewal policy: every successful heartbeat
        advances ``expires_at`` to ``now + ttl_seconds``. M2 swaps
        in the registry-driven ``lease_renewal_policy`` factory
        protocol.
    """

    __tablename__ = "resources_lease"

    lease_id = Column(UUIDType(binary=False), primary_key=True)
    reservation_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    resource_id = Column(UUIDType(binary=False), nullable=False)
    lease_kind = Column(String(32), nullable=False, default="fixed")
    ttl_seconds = Column(Integer, nullable=False, default=60)
    state = Column(
        Enum(LeaseState, name=LEASE_STATE_ENUM),
        nullable=False,
        default=LeaseState.ACTIVE,
    )
    attached_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    last_heartbeat_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    closed_at = Column(UtcDateTime(timezone=True), nullable=True)
    close_reason = Column(String(64), nullable=True)
    heartbeat_count = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "reservation_id",
            name="uq_resources_lease_reservation",
        ),
        Index(
            "ix_resources_lease_state_expires",
            "state", "expires_at",
        ),
        Index(
            "ix_resources_lease_resource",
            "resource_id",
        ),
    )
