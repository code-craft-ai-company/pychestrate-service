"""
.. module:: orchestration.infra.environment.models
    :synopsis: SQLAlchemy models + enums for the environment registry.
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
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class EnvironmentState(str, enum.Enum):
    """
        Lifecycle of an environment.
    """
    ACTIVE = "active"
    FROZEN = "frozen"
    ARCHIVED = "archived"
    DESTROYED = "destroyed"


class EnvironmentEventKind(str, enum.Enum):
    """
        Event kind recorded on the per-environment ledger.
    """
    DECLARED = "declared"
    UPDATED = "updated"
    ARCHIVED = "archived"
    FROZEN = "frozen"
    UNFROZEN = "unfrozen"
    APPLIED = "applied"
    DESTROYED = "destroyed"


ENVIRONMENT_STATE_ENUM = "orch_environment_state"
ENVIRONMENT_EVENT_KIND_ENUM = "orch_environment_event_kind"


class Environment(PychestratePhase1Base, SerializableModel):
    """
        One environment row.
    """

    __tablename__ = "orch_environment"

    environment_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    kind_name = Column(String(64), nullable=False, default="")
    name = Column(String(128), nullable=False, default="")
    state = Column(
        Enum(EnvironmentState, name=ENVIRONMENT_STATE_ENUM),
        nullable=False,
        default=EnvironmentState.ACTIVE,
    )
    attrs = Column(JSON, nullable=False, default=dict)
    frozen_by = Column(UUIDType(binary=False), nullable=True)
    frozen_reason = Column(Text, nullable=True)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    last_applied_run_id = Column(UUIDType(binary=False), nullable=True)
    last_output_digest_sha256 = Column(String(64), nullable=False, default="")
    last_applied_at = Column(DateTime(timezone=True), nullable=True)
    archived_reason = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    destroyed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "kind_name", "name",
            name="uq_orch_environment_project_kind_name",
        ),
        Index("ix_orch_environment_project_kind", "project_id", "kind_name"),
        Index("ix_orch_environment_project_state", "project_id", "state"),
    )


class EnvironmentHistory(PychestratePhase1Base, SerializableModel):
    """
        Append-only ledger of state-transitioning events on an
        environment.
    """

    __tablename__ = "orch_environment_history"

    history_id = Column(UUIDType(binary=False), primary_key=True)
    environment_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_environment.environment_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_kind = Column(
        Enum(EnvironmentEventKind, name=ENVIRONMENT_EVENT_KIND_ENUM),
        nullable=False,
    )
    actor_id = Column(UUIDType(binary=False), nullable=True)
    run_id = Column(UUIDType(binary=False), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    at_ts = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_orch_environment_history_env_at",
            "environment_id", "at_ts",
        ),
    )
