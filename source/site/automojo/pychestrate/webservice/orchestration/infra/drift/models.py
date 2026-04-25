"""
.. module:: orchestration.infra.drift.models
    :synopsis: SQLAlchemy models + enums for drift detection.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class DriftRunState(str, enum.Enum):
    """
        Lifecycle of a drift run.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INGEST_FAILED = "ingest_failed"
    SKIPPED = "skipped"


class DriftTriggerKind(str, enum.Enum):
    """
        How a drift run was triggered.
    """
    SCHEDULE = "schedule"
    MANUAL = "manual"


DRIFT_RUN_STATE_ENUM = "orch_drift_run_state"
DRIFT_TRIGGER_KIND_ENUM = "orch_drift_trigger_kind"


class DriftSchedule(PychestratePhase1Base, SerializableModel):
    """
        Per-(project, environment) drift schedule.
    """

    __tablename__ = "orch_drift_schedule"

    project_id = Column(UUIDType(binary=False), nullable=False)
    environment_id = Column(UUIDType(binary=False), nullable=False)
    checker_name = Column(String(64), nullable=False, default="")
    cron_expression = Column(String(128), nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(UUIDType(binary=False), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "environment_id",
            name="pk_orch_drift_schedule",
        ),
    )


class DriftRun(PychestratePhase1Base, SerializableModel):
    """
        One drift execution.
    """

    __tablename__ = "orch_drift_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    environment_id = Column(UUIDType(binary=False), nullable=False)
    checker_name = Column(String(64), nullable=False, default="")
    layer5_run_id = Column(UUIDType(binary=False), nullable=True)
    state = Column(
        Enum(DriftRunState, name=DRIFT_RUN_STATE_ENUM),
        nullable=False,
        default=DriftRunState.PENDING,
    )
    trigger_kind = Column(
        Enum(DriftTriggerKind, name=DRIFT_TRIGGER_KIND_ENUM),
        nullable=False,
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    ran_at = Column(DateTime(timezone=True), nullable=True)
    drift_count = Column(Integer, nullable=True)
    added = Column(Integer, nullable=True)
    changed = Column(Integer, nullable=True)
    destroyed = Column(Integer, nullable=True)
    diff_digest_sha256 = Column(String(64), nullable=False, default="")
    report_blob_key = Column(Text, nullable=True)
    report_payload = Column(JSON, nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index(
            "ix_orch_drift_run_env_scheduled",
            "environment_id", "scheduled_for",
        ),
        Index("ix_orch_drift_run_state", "state"),
    )


class DriftTickLedger(PychestratePhase1Base, SerializableModel):
    """
        Exactly-once dispatch ledger keyed on
        ``(project_id, environment_id, scheduled_for)``.
    """

    __tablename__ = "orch_drift_tick_ledger"

    project_id = Column(UUIDType(binary=False), nullable=False)
    environment_id = Column(UUIDType(binary=False), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    run_id = Column(UUIDType(binary=False), nullable=False)
    recorded_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "environment_id", "scheduled_for",
            name="pk_orch_drift_tick_ledger",
        ),
    )
