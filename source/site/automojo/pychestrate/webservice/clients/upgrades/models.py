"""
.. module:: clients.upgrades.models
    :synopsis: SQLAlchemy models for the agent upgrade channel.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


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
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.clients.upgrades.enums import (
    OFFER_OUTCOME_ENUM,
    OfferOutcome,
    ROLLOUT_STATE_ENUM,
    RolloutState,
    STAGE_STATE_ENUM,
    StageState,
)
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class AgentRollout(PychestratePhase1Base, SerializableModel):
    """
        Top-level rollout row.
    """

    __tablename__ = "agent_rollout"

    rollout_id = Column(UUIDType(binary=False), primary_key=True)
    version = Column(String(64), nullable=False)
    artifact_source = Column(String(64), nullable=False)
    artifact_ref = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False)
    signature = Column(Text, nullable=False, default="")
    issued_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    state = Column(
        Enum(RolloutState, name=ROLLOUT_STATE_ENUM),
        nullable=False,
        default=RolloutState.DRAFT,
    )
    created_by = Column(UUIDType(binary=False), nullable=True)
    halted_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_agent_rollout_version", "version"),
        Index("ix_agent_rollout_state", "state"),
    )


class AgentRolloutStage(PychestratePhase1Base, SerializableModel):
    """
        Per-stage row inside a rollout.
    """

    __tablename__ = "agent_rollout_stage"

    stage_id = Column(UUIDType(binary=False), primary_key=True)
    rollout_id = Column(
        UUIDType(binary=False),
        ForeignKey("agent_rollout.rollout_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_index = Column(Integer, nullable=False)
    rollout_policy = Column(String(64), nullable=False)
    policy_params = Column(JSON, nullable=False, default=dict)
    target_size = Column(Integer, nullable=False, default=0)
    state = Column(
        Enum(StageState, name=STAGE_STATE_ENUM),
        nullable=False,
        default=StageState.PENDING,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    deferred_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "rollout_id", "stage_index",
            name="uq_agent_rollout_stage_rollout_index",
        ),
    )


class AgentUpgradeOffer(PychestratePhase1Base, SerializableModel):
    """
        Per-(stage, client) offer row.
    """

    __tablename__ = "agent_upgrade_offer"

    offer_id = Column(UUIDType(binary=False), primary_key=True)
    stage_id = Column(
        UUIDType(binary=False),
        ForeignKey("agent_rollout_stage.stage_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(String(128), nullable=False)
    version = Column(String(64), nullable=False)
    offered_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    outcome = Column(
        Enum(OfferOutcome, name=OFFER_OUTCOME_ENUM),
        nullable=False,
        default=OfferOutcome.OFFERED,
    )
    outcome_at = Column(DateTime(timezone=True), nullable=True)
    outcome_detail = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "stage_id", "client_id",
            name="uq_agent_upgrade_offer_stage_client",
        ),
        Index(
            "ix_agent_upgrade_offer_outcome",
            "outcome",
        ),
    )


class AgentPodPin(PychestratePhase1Base, SerializableModel):
    """
        Pin row keyed by the pod identifier; pins block any
        upgrade offer whose version does not match.
    """

    __tablename__ = "agent_pod_pin"

    pod_id = Column(String(128), primary_key=True)
    pinned_version = Column(String(64), nullable=False)
    set_by = Column(UUIDType(binary=False), nullable=True)
    set_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    reason = Column(Text, nullable=True)
