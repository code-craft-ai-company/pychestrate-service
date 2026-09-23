"""
.. module:: resources.health.models
    :synopsis: SQLAlchemy model + enum for resource-health rows.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ProbeOutcome(str, enum.Enum):
    """
        Outcome of a single probe execution.
    """
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


PROBE_OUTCOME_ENUM = "resources_health_probe_outcome"


class ResourceHealth(PychestratePhase1Base, SerializableModel):
    """
        One health record per resource. M1 stores rolling pass /
        fail counters and the next-probe timestamp; the M2
        quarantine state machine reads ``consecutive_failures``
        and the deferred-quarantine flag.
    """

    __tablename__ = "resources_resource_health"

    health_id = Column(UUIDType(binary=False), primary_key=True)
    resource_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    probe_name = Column(String(64), nullable=False, default="")
    probe_period_seconds = Column(Integer, nullable=False, default=60)
    last_outcome = Column(
        Enum(ProbeOutcome, name=PROBE_OUTCOME_ENUM),
        nullable=False,
        default=ProbeOutcome.UNKNOWN,
    )
    last_probe_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_pass_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_fail_at = Column(UtcDateTime(timezone=True), nullable=True)
    next_probe_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    pass_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    last_payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            name="uq_resources_resource_health_resource",
        ),
        Index(
            "ix_resources_resource_health_next_probe",
            "next_probe_at", "probe_name",
        ),
        Index(
            "ix_resources_resource_health_project",
            "project_id",
        ),
    )
