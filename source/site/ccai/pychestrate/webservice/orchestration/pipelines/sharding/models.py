"""
.. module:: orchestration.pipelines.sharding.models
    :synopsis: SQLAlchemy models + enums for shard-set / shard-spec rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ShardSetState(str, enum.Enum):
    """
        Lifecycle of a shard set.
    """
    EXPANDING = "expanding"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ShardState(str, enum.Enum):
    """
        Lifecycle of a single shard. Mirrors the Layer-5 run
        state in M2; M1 only tracks ``PENDING`` /
        ``DISPATCHED`` / ``CANCELLED``.
    """
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


SHARD_SET_STATE_ENUM = "orch_shard_set_state"
SHARD_STATE_ENUM = "orch_shard_state"


class ShardSet(PychestratePhase1Base, SerializableModel):
    """
        Wrapper row for a fan-out from one matrix expansion.
    """

    __tablename__ = "orch_shard_set"

    shard_set_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    parent_kind = Column(String(32), nullable=False)
    parent_id = Column(UUIDType(binary=False), nullable=False)
    strategy_name = Column(String(64), nullable=False)
    matrix_spec_canonical_sha256 = Column(String(64), nullable=False)
    state = Column(
        Enum(ShardSetState, name=SHARD_SET_STATE_ENUM),
        nullable=False,
        default=ShardSetState.EXPANDING,
    )
    fail_fast = Column(Boolean, nullable=False, default=False)
    allow_partial_success = Column(Boolean, nullable=False, default=False)
    min_success_fraction = Column(Float, nullable=False, default=1.0)
    shard_count = Column(Integer, nullable=False, default=0)
    started_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_orch_shard_set_project", "project_id"),
        Index("ix_orch_shard_set_parent", "parent_kind", "parent_id"),
    )


class ShardSpec(PychestratePhase1Base, SerializableModel):
    """
        One shard inside a shard set. ``shard_id`` is a 16-char
        hex digest derived from the canonicalized dimension
        values; together with ``shard_set_id`` it forms the
        composite PK.
    """

    __tablename__ = "orch_shard_spec"

    shard_set_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_shard_set.shard_set_id", ondelete="CASCADE"),
        nullable=False,
    )
    shard_id = Column(String(16), nullable=False)
    parallel_group = Column(String(64), nullable=False, default="")
    sequence_in_group = Column(Integer, nullable=False, default=0)
    dimension_values = Column(JSON, nullable=False, default=dict)
    canonical_dims_json = Column(Text, nullable=False, default="{}")
    state = Column(
        Enum(ShardState, name=SHARD_STATE_ENUM),
        nullable=False,
        default=ShardState.PENDING,
    )
    run_id = Column(UUIDType(binary=False), nullable=True)
    dispatched_at = Column(UtcDateTime(timezone=True), nullable=True)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "shard_set_id", "shard_id",
            name="pk_orch_shard_spec",
        ),
        Index(
            "ix_orch_shard_spec_set_group_seq",
            "shard_set_id", "parallel_group", "sequence_in_group",
        ),
        Index("ix_orch_shard_spec_run", "run_id"),
    )
