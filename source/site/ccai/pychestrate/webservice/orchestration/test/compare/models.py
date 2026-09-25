"""
.. module:: orchestration.test.compare.models
    :synopsis: SQLAlchemy model + enum for compare reports.
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
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class CompareStatus(str, enum.Enum):
    """
        Lifecycle of a compare report.
    """
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"


COMPARE_STATUS_ENUM = "orch_compare_status"


class CompareReport(PychestratePhase1Base, SerializableModel):
    """
        Cached per-run pairwise diff report. ``per_test``
        payload lives inline as JSON for M1; the M2 cache layer
        moves it into the object store and replaces this column
        with a blob key.
    """

    __tablename__ = "orch_compare_report"

    report_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    base_run_id = Column(UUIDType(binary=False), nullable=False)
    candidate_run_id = Column(UUIDType(binary=False), nullable=False)
    status = Column(
        Enum(CompareStatus, name=COMPARE_STATUS_ENUM),
        nullable=False,
        default=CompareStatus.BUILDING,
    )
    per_test_count = Column(Integer, nullable=False, default=0)
    per_test_payload = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    note = Column(Text, nullable=False, default="")
    computed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "base_run_id", "candidate_run_id",
            name="uq_orch_compare_report_run_pair",
        ),
        Index(
            "ix_orch_compare_report_project",
            "project_id",
        ),
    )
