"""
.. module:: agents.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for Layer-3 agent features.

.. moduleauthor:: Code Craft AI LLC
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
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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


_Json = JSON().with_variant(JSONB(), "postgresql")


class FrameDirection(enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class RolloutState(enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    COMPLETED = "COMPLETED"


class UpgradeOfferOutcome(enum.Enum):
    OFFERED = "OFFERED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEFERRED = "DEFERRED"
    EXPIRED = "EXPIRED"
    SHA256_MISMATCH = "SHA256_MISMATCH"


class ClientSession(PychestratePhase1Base, SerializableModel):
    """
        3-client-agent-protocol session row.
    """
    __tablename__ = "agents_client_sessions"

    session_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(UUIDType(binary=False), nullable=True)
    transport_name = Column(String(64), nullable=False)
    remote_addr = Column(String(128), nullable=True)
    cert_serial = Column(String(64), nullable=True)
    opened_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    closed_at = Column(UtcDateTime(timezone=True), nullable=True)
    close_code = Column(String(64), nullable=True)
    enrollment_nonce = Column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_agents_client_sessions_client", "client_id"),
    )


class ClientFrameAudit(PychestratePhase1Base, SerializableModel):
    """
        Frame-level audit row.
    """
    __tablename__ = "agents_client_frame_audit"

    frame_id = Column(UUIDType(binary=False), primary_key=True)
    session_id = Column(
        UUIDType(binary=False),
        ForeignKey("agents_client_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(64), nullable=False)
    direction = Column(Enum(FrameDirection, name="agents_frame_direction"), nullable=False)
    size_bytes = Column(Integer(), nullable=False, default=0)
    received_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    accepted = Column(Boolean(), nullable=False, default=True)
    reject_reason = Column(String(256), nullable=True)


class ClientCapability(PychestratePhase1Base, SerializableModel):
    """
        3-client-capability-advertisement row.
    """
    __tablename__ = "agents_client_capabilities"

    capability_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(UUIDType(binary=False), nullable=False)
    kind = Column(String(64), nullable=False)
    value_json = Column(_Json, nullable=False, default=dict)
    sensitive_ref = Column(String(256), nullable=True)
    revision_token = Column(String(64), nullable=False, default="")
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("client_id", "kind", name="uq_agents_capability_client_kind"),
        Index("ix_agents_capability_client", "client_id"),
    )


class ClientInventoryChangeLog(PychestratePhase1Base, SerializableModel):
    """
        3-client-inventory-ui append-only change log.
    """
    __tablename__ = "agents_client_inventory_change_log"

    change_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=True)
    change_kind = Column(String(64), nullable=False)
    payload_summary = Column(_Json, nullable=False, default=dict)
    logged_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_agents_inventory_change_client", "client_id"),
        Index("ix_agents_inventory_change_logged", "logged_at"),
    )


class AgentRollout(PychestratePhase1Base, SerializableModel):
    """
        3-agent-upgrade-channel rollout record.
    """
    __tablename__ = "agents_rollouts"

    rollout_id = Column(UUIDType(binary=False), primary_key=True)
    version = Column(String(64), nullable=False)
    artifact_source = Column(String(64), nullable=False)
    artifact_ref = Column(String(512), nullable=False)
    signature = Column(LargeBinary(), nullable=True)
    state = Column(
        Enum(RolloutState, name="agents_rollout_state"),
        nullable=False,
        default=RolloutState.DRAFT,
    )
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)


class RolloutStageState(enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    HELD = "HELD"
    COMPLETED = "COMPLETED"
    HALTED = "HALTED"


class AgentRolloutStage(PychestratePhase1Base, SerializableModel):
    """
        Per-stage row for multi-wave rollouts (M2).
    """
    __tablename__ = "agents_rollout_stages"

    stage_id = Column(UUIDType(binary=False), primary_key=True)
    rollout_id = Column(
        UUIDType(binary=False),
        ForeignKey("agents_rollouts.rollout_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_index = Column(Integer(), nullable=False)
    rollout_policy = Column(String(64), nullable=False)
    target_size = Column(Integer(), nullable=False, default=10)
    state = Column(
        Enum(RolloutStageState, name="agents_rollout_stage_state"),
        nullable=False,
        default=RolloutStageState.PENDING,
    )
    success_count = Column(Integer(), nullable=False, default=0)
    failure_count = Column(Integer(), nullable=False, default=0)
    deferred_count = Column(Integer(), nullable=False, default=0)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(UtcDateTime(timezone=True), nullable=True)
    completed_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "rollout_id", "stage_index", name="uq_agents_rollout_stage_index",
        ),
    )


class AgentPodPin(PychestratePhase1Base, SerializableModel):
    """
        Per-pod version pin; rollout stages honor active pins.
    """
    __tablename__ = "agents_pod_pins"

    pod_id = Column(UUIDType(binary=False), primary_key=True)
    pinned_version = Column(String(64), nullable=False)
    set_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    reason = Column(String(256), nullable=False, default="")


class AgentUpgradeOffer(PychestratePhase1Base, SerializableModel):
    """
        Per-client offer emitted during a rollout.
    """
    __tablename__ = "agents_upgrade_offers"

    offer_id = Column(UUIDType(binary=False), primary_key=True)
    rollout_id = Column(
        UUIDType(binary=False),
        ForeignKey("agents_rollouts.rollout_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(UUIDType(binary=False), nullable=False)
    version = Column(String(64), nullable=False)
    outcome = Column(
        Enum(UpgradeOfferOutcome, name="agents_upgrade_offer_outcome"),
        nullable=False,
        default=UpgradeOfferOutcome.OFFERED,
    )
    offered_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at = Column(UtcDateTime(timezone=True), nullable=True)
    detail = Column(Text(), nullable=True)

    __table_args__ = (
        Index("ix_agents_upgrade_offer_rollout", "rollout_id"),
        Index("ix_agents_upgrade_offer_client", "client_id"),
    )
