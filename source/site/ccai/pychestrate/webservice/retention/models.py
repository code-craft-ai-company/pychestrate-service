"""
.. module:: retention.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-retention-policies feature.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


_JsonPayload = JSON().with_variant(JSONB(), "postgresql")


class PolicyState(enum.Enum):
    """
        Lifecycle state for a :class:`RetentionPolicy`.
    """
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class PolicyScopeLevel(enum.Enum):
    """
        Scope level for a :class:`RetentionPolicy`.
    """
    SYSTEM = "SYSTEM"
    PROJECT = "PROJECT"


class ActionOutcome(enum.Enum):
    """
        Outcome of a single action step against a single entity.
    """
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SelectorClause:
    """
        Declarative selection clause for retention matching.

        :param tag_expression: Boolean tag expression (M2 uses this).
        :param age_days: Minimum age in days.
        :param size_bytes_over: Minimum size threshold.
        :param project_ids: Restrict to given project ids.
    """
    tag_expression: str = ""
    age_days: int = 0
    size_bytes_over: int = 0
    project_ids: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ActionStep:
    """
        One step in the action chain.

        :param action_name: Registered action name.
        :param parameters: Action-specific parameters.
        :param wait_days_after_previous: Days to defer after previous step.
    """
    action_name: str
    parameters: Mapping[str, Any]
    wait_days_after_previous: int = 0


class RetentionPolicy(PychestratePhase1Base, SerializableModel):
    """
        A retention policy record.
    """

    __tablename__ = "retention_policies"

    policy_id = Column(UUIDType(binary=False), primary_key=True)
    name = Column(String(128), nullable=False)
    data_class = Column(String(64), nullable=False)
    scope_level = Column(
        Enum(PolicyScopeLevel, name="retention_policy_scope_level"),
        nullable=False,
    )
    project_id = Column(UUIDType(binary=False), nullable=True)
    selector = Column(_JsonPayload, nullable=False, default=dict)
    action_chain = Column(_JsonPayload, nullable=False, default=list)
    interval_minutes = Column(Integer(), nullable=False, default=1440)
    batch_size = Column(Integer(), nullable=False, default=500)
    max_attempts = Column(Integer(), nullable=False, default=3)
    state = Column(
        Enum(PolicyState, name="retention_policy_state"),
        nullable=False,
        default=PolicyState.DRAFT,
    )
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    published_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "scope_level", "project_id", "name",
            name="uq_retention_policy_name",
        ),
        Index("ix_retention_policy_state", "state"),
        Index("ix_retention_policy_data_class", "data_class"),
    )


class RetentionRunRecord(PychestratePhase1Base, SerializableModel):
    """
        A single run of a published :class:`RetentionPolicy`.
    """

    __tablename__ = "retention_runs"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    policy_id = Column(
        UUIDType(binary=False),
        ForeignKey("retention_policies.policy_id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    matched_count = Column(Integer(), nullable=False, default=0)
    actioned_count = Column(Integer(), nullable=False, default=0)
    skipped_count = Column(Integer(), nullable=False, default=0)
    failed_count = Column(Integer(), nullable=False, default=0)
    error_summary = Column(Text(), nullable=True)

    __table_args__ = (
        Index("ix_retention_runs_policy", "policy_id"),
    )


class RetentionActionResult(PychestratePhase1Base, SerializableModel):
    """
        One row per action application during a :class:`RetentionRunRecord`.
    """

    __tablename__ = "retention_action_results"

    result_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(
        UUIDType(binary=False),
        ForeignKey("retention_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id = Column(String(128), nullable=False)
    action_name = Column(String(64), nullable=False)
    outcome = Column(
        Enum(ActionOutcome, name="retention_action_outcome"),
        nullable=False,
    )
    reason = Column(Text(), nullable=True)
    terminal = Column(String(8), nullable=False, default="false")
    applied_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_retention_action_results_run", "run_id"),
    )
