"""
.. module:: orchestration.build.models
    :synopsis: SQLAlchemy models + enum for build-runs.
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
    ForeignKey,
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


class BuildRunState(str, enum.Enum):
    """
        Lifecycle of a build run.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


BUILD_RUN_STATE_ENUM = "orch_build_run_state"


class BuildRun(PychestratePhase1Base, SerializableModel):
    """
        One build execution.
    """

    __tablename__ = "orch_build_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    runner_kind = Column(String(64), nullable=False, default="")
    repro_digest_sha256 = Column(String(64), nullable=False, default="")
    state = Column(
        Enum(BuildRunState, name=BUILD_RUN_STATE_ENUM),
        nullable=False,
        default=BuildRunState.PENDING,
    )
    layer5_run_id = Column(UUIDType(binary=False), nullable=True)
    pipeline_run_id = Column(UUIDType(binary=False), nullable=True)
    pipeline_step_run_id = Column(UUIDType(binary=False), nullable=True)
    actor_id = Column(UUIDType(binary=False), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")
    inputs = Column(JSON, nullable=False, default=dict)
    annotations = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_orch_build_run_project_state", "project_id", "state"),
        Index("ix_orch_build_run_digest", "repro_digest_sha256"),
        Index("ix_orch_build_run_layer5", "layer5_run_id"),
    )


class BuildToolchainSnapshot(PychestratePhase1Base, SerializableModel):
    """
        One toolchain entry recorded against a build run. The
        composite PK ``(run_id, toolchain_key)`` keeps a stable
        upsert key.
    """

    __tablename__ = "orch_build_toolchain_snapshot"

    run_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_build_run.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    toolchain_key = Column(String(128), nullable=False)
    version = Column(String(128), nullable=False, default="")
    fingerprint_sha256 = Column(String(64), nullable=False, default="")

    __table_args__ = (
        PrimaryKeyConstraint(
            "run_id", "toolchain_key",
            name="pk_orch_build_toolchain_snapshot",
        ),
    )


class BuildCacheScope(PychestratePhase1Base, SerializableModel):
    """
        Cache scope row recorded for diagnostics. M1 persists
        only the scope-name + bytes-allocated counter; the M2
        cache backend writes through these rows.
    """

    __tablename__ = "orch_build_cache_scope"

    scope_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    scope_name = Column(String(128), nullable=False, default="")
    bytes_allocated = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_orch_build_cache_scope_project", "project_id"),
    )
