"""
.. module:: backup.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model + enum for backup records.

.. moduleauthor:: Automation Mojo LLC

The ``backup_record`` table holds one row per triggered backup
run. The p21d milestone is a manual-trigger baseline -- scheduled
fulls / incrementals and restore-drill bookkeeping land with the
scheduler follow-on. The row is deliberately self-contained: the
``manifest`` JSON column carries the substrate inventory so a
read does not have to fan out across substrate rows.
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
    Integer,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class BackupStatus(str, enum.Enum):
    """
        Lifecycle of a backup run.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


BACKUP_STATUS_ENUM = "backup_record_status"


class BackupRecord(PychestratePhase1Base, SerializableModel):
    """
        One triggered backup run.
    """

    __tablename__ = "backup_record"

    backup_id = Column(UUIDType(binary=False), primary_key=True)
    status = Column(
        Enum(BackupStatus, name=BACKUP_STATUS_ENUM),
        nullable=False,
        default=BackupStatus.PENDING,
    )
    backend = Column(String(64), nullable=False, default="")
    archive_uri = Column(Text, nullable=True)
    archive_sha256 = Column(String(64), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    manifest = Column(JSON, nullable=False, default=dict)
    error_detail = Column(Text, nullable=True)
    note = Column(Text, nullable=False, default="")
    created_by = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_backup_record_status", "status"),
        Index("ix_backup_record_created_at", "created_at"),
    )
