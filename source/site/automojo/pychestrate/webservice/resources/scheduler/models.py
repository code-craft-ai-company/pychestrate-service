"""
.. module:: resources.scheduler.models
    :synopsis: SQLAlchemy model + enum for scheduler entries.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class SchedulerEntryState(str, enum.Enum):
    """
        Lifecycle of a scheduler queue entry.

        * ``QUEUED`` — waiting for capacity on the pool.
        * ``DISPATCHED`` — handed to checkout for grant; terminal.
        * ``CANCELLED`` — caller dropped before grant; terminal.
    """
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


SCHEDULER_ENTRY_STATE_ENUM = "resources_scheduler_entry_state"


class SchedulerEntry(PychestratePhase1Base, SerializableModel):
    """
        Persistent record of a reservation waiting on a pool.

        M1 honors ``algorithm`` only as a snapshot for future
        replay — dispatch is hard-wired FIFO. ``priority``,
        ``fair_share_*`` and ``deadline_at`` are persisted so the
        M2 algorithms can read existing rows after the migration
        without a back-fill.
    """

    __tablename__ = "resources_scheduler_entry"

    entry_id = Column(UUIDType(binary=False), primary_key=True)
    reservation_id = Column(UUIDType(binary=False), nullable=False)
    pool_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    algorithm = Column(String(64), nullable=False, default="fifo")
    priority = Column(Integer, nullable=False, default=50)
    fair_share_key = Column(String(128), nullable=True)
    fair_share_weight = Column(Float, nullable=False, default=1.0)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    enqueued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    state = Column(
        Enum(SchedulerEntryState, name=SCHEDULER_ENTRY_STATE_ENUM),
        nullable=False,
        default=SchedulerEntryState.QUEUED,
    )
    version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "reservation_id",
            name="uq_resources_scheduler_entry_reservation",
        ),
        Index(
            "ix_resources_scheduler_entry_pool_state_priority",
            "pool_id", "state", "priority", "enqueued_at",
        ),
        Index(
            "ix_resources_scheduler_entry_pool_state_deadline",
            "pool_id", "state", "deadline_at",
        ),
        Index(
            "ix_resources_scheduler_entry_fair_share",
            "fair_share_key", "state",
        ),
    )
