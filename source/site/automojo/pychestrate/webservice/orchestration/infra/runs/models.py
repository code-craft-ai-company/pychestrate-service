"""
.. module:: orchestration.infra.runs.models
    :synopsis: SQLAlchemy models + enums for infra runs.
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


class InfraAction(str, enum.Enum):
    """
        Action requested on an infra run.
    """
    PLAN = "plan"
    APPLY = "apply"
    DESTROY = "destroy"


class InfraRunState(str, enum.Enum):
    """
        Lifecycle of an infra run. Mirrors Layer-5 plus
        ``REJECTED_BY_GUARD`` for guard rejections.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED_BY_GUARD = "rejected_by_guard"


INFRA_ACTION_ENUM = "orch_infra_action"
INFRA_RUN_STATE_ENUM = "orch_infra_run_state"


class InfraRun(PychestratePhase1Base, SerializableModel):
    """
        One infra-run record.
    """

    __tablename__ = "orch_infra_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    environment_id = Column(UUIDType(binary=False), nullable=False)
    driver_name = Column(String(64), nullable=False, default="")
    action = Column(
        Enum(InfraAction, name=INFRA_ACTION_ENUM),
        nullable=False,
    )
    state = Column(
        Enum(InfraRunState, name=INFRA_RUN_STATE_ENUM),
        nullable=False,
        default=InfraRunState.PENDING,
    )
    layer5_run_id = Column(UUIDType(binary=False), nullable=True)
    actor_id = Column(UUIDType(binary=False), nullable=True)
    actor_role_set_csv = Column(Text, nullable=False, default="")
    inputs = Column(JSON, nullable=False, default=dict)
    inputs_canonical_sha256 = Column(String(64), nullable=False, default="")
    plan_summary = Column(JSON, nullable=True)
    plan_artifact_ref = Column(Text, nullable=True)
    plan_diff_digest_sha256 = Column(String(64), nullable=False, default="")
    plan_issued_at = Column(DateTime(timezone=True), nullable=True)
    replay_of = Column(UUIDType(binary=False), nullable=True)
    output_digest_sha256 = Column(String(64), nullable=False, default="")
    failing_guard_rule_id = Column(String(128), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index(
            "ix_orch_infra_run_project_env_state",
            "project_id", "environment_id", "state",
        ),
        Index("ix_orch_infra_run_replay_of", "replay_of"),
        Index(
            "ix_orch_infra_run_driver_state",
            "driver_name", "state",
        ),
    )
