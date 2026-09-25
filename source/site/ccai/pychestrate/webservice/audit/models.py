"""
.. module:: audit.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-audit-log feature.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class AuditSinkOutboxStatus(enum.Enum):
    """
        Lifecycle state for a row in the per-sink outbox.
    """
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class AuditRecord(PychestratePhase1Base, SerializableModel):
    """
        Canonical INSERT-only audit record row.
    """

    __tablename__ = "audit_records"

    sequence_number = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    record_id = Column(UUIDType(binary=False), nullable=False, unique=True)
    kind = Column(String(128), nullable=False)
    source_topic = Column(String(128), nullable=False)
    source_event_id = Column(UUIDType(binary=False), nullable=False, unique=True)
    actor_user_id = Column(UUIDType(binary=False), nullable=True)
    actor_service_identity = Column(String(128), nullable=True)
    target_ref = Column(String(256), nullable=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    payload_hash = Column(LargeBinary(64), nullable=False)
    previous_hash = Column(LargeBinary(64), nullable=False)
    record_hash = Column(LargeBinary(64), nullable=False)
    written_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_audit_records_kind_written_at", "kind", "written_at"),
        Index("ix_audit_records_actor_written_at", "actor_user_id", "written_at"),
        Index("ix_audit_records_target_ref_written_at", "target_ref", "written_at"),
    )


class AuditSinkRegistration(PychestratePhase1Base, SerializableModel):
    """
        Live view of registered audit sinks.
    """

    __tablename__ = "audit_sink_registrations"

    sink_name = Column(String(128), primary_key=True)
    precedence = Column(Integer, nullable=False)
    is_canonical = Column(Boolean, nullable=False, default=False)
    capabilities_json = Column(JSON, nullable=False, default=dict)


class AuditSinkOutbox(PychestratePhase1Base, SerializableModel):
    """
        Per-sink durable outbox row.
    """

    __tablename__ = "audit_sink_outbox"

    outbox_id = Column(UUIDType(binary=False), primary_key=True)
    sink_name = Column(String(128), nullable=False)
    sequence_number = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    status = Column(Enum(AuditSinkOutboxStatus, name="audit_sink_outbox_status"), nullable=False)
    enqueued_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    next_attempt_at = Column(UtcDateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)


class AuditEventCatalogEntry(PychestratePhase1Base, SerializableModel):
    """
        Registered audit kinds — populated at startup from the resource extensions.
    """

    __tablename__ = "audit_event_catalog"

    kind = Column(String(128), primary_key=True)
    source_name = Column(String(128), nullable=True)
    payload_schema = Column(JSON, nullable=False, default=dict)
    is_reserved = Column(Boolean, nullable=False, default=False)
