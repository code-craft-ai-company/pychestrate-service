"""
.. module:: jobs.cancel.models
    :synopsis: SQLAlchemy model for cancel_request.
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
    Index,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class CancelStatus(str, enum.Enum):
    """
        Lifecycle for a cancel-request row.
    """
    PENDING = "pending"
    TRANSMITTED = "transmitted"
    ACKED = "acked"
    FAILED = "failed"
    QUEUED_OFFLINE = "queued_offline"


CANCEL_STATUS_ENUM = "jobs_cancel_status"


class CancelRequest(PychestratePhase1Base, SerializableModel):
    """
        One row per cancel-RPC request. ``run_id`` carries a unique
        constraint at the application level — only one open
        cancel request per run; once acked / failed the unique
        slot can be reused (M2 enforces this with a partial unique
        index on Postgres; SQLite falls back to a simple unique
        check at the service layer).
    """

    __tablename__ = "jobs_cancel_request"

    request_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    requested_by = Column(UUIDType(binary=False), nullable=True)
    reason = Column(String(512), nullable=False, default="")
    status = Column(
        Enum(CancelStatus, name=CANCEL_STATUS_ENUM),
        nullable=False,
        default=CancelStatus.PENDING,
    )
    requested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    transmitted_at = Column(DateTime(timezone=True), nullable=True)
    acked_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_jobs_cancel_request_run", "run_id"),
        Index("ix_jobs_cancel_request_status", "status"),
    )
