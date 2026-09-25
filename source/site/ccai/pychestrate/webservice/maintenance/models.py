"""
.. module:: maintenance.models
    :synopsis: SQLAlchemy models for maintenance-mode rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class MaintenanceModeRow(PychestratePhase1Base, SerializableModel):
    """
        Persistent state for a single maintenance scope.
        ``scope`` is the PK — values are ``"service"`` for the
        global gate or ``"project:<slug>"`` for a per-project
        scope.
    """

    __tablename__ = "maintenance_mode"

    scope = Column(String(160), primary_key=True)
    mode = Column(String(16), nullable=False, default="active")
    reason = Column(Text, nullable=False, default="")
    ends_at = Column(UtcDateTime(timezone=True), nullable=True)
    changed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    changed_by = Column(UUIDType(binary=False), nullable=True)
    version = Column(Integer, nullable=False, default=1)


class MaintenanceModeAudit(PychestratePhase1Base, SerializableModel):
    """
        Append-only audit row — every state transition gets a
        record so operators can reconstruct the timeline.
    """

    __tablename__ = "maintenance_mode_audit"

    audit_id = Column(UUIDType(binary=False), primary_key=True)
    scope = Column(String(160), nullable=False)
    from_mode = Column(String(16), nullable=False)
    to_mode = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False, default="")
    ends_at = Column(UtcDateTime(timezone=True), nullable=True)
    actor_user_id = Column(UUIDType(binary=False), nullable=True)
    changed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_maintenance_mode_audit_scope_changed",
            "scope", "changed_at",
        ),
    )
