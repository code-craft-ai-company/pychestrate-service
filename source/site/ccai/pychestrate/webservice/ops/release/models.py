"""
.. module:: ops.release.models
    :synopsis: Release-channels SQLAlchemy models + enums.
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
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ReleaseComponent(str, enum.Enum):
    """
        Component the release applies to. M1 ships SERVICE +
        AGENT; future major component types land here.
    """
    SERVICE = "service"
    AGENT = "agent"


class ReleaseChannel(str, enum.Enum):
    """
        Release channel.
    """
    CANARY = "canary"
    BETA = "beta"
    STABLE = "stable"


class ReleaseStatus(str, enum.Enum):
    """
        Release lifecycle status. M1 sets ACTIVE on publish;
        M2 transitions to SUPERSEDED on promotion past 100% of
        a successor + ROLLED_BACK / WITHDRAWN.
    """
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"
    WITHDRAWN = "withdrawn"


class StageEventKind(str, enum.Enum):
    """
        Append-only stage-event kinds.
    """
    PUBLISHED = "published"
    PROMOTED = "promoted"
    DEMOTED = "demoted"
    ROLLED_BACK = "rolled_back"
    AUTO_HALTED = "auto_halted"


class ConsumerOutcome(str, enum.Enum):
    """
        Consumer-reported outcome for a release.
    """
    SUCCESS = "success"
    FAILURE = "failure"
    DEFERRED = "deferred"


RELEASE_COMPONENT_ENUM = "release_component"
RELEASE_CHANNEL_ENUM = "release_channel"
RELEASE_STATUS_ENUM = "release_status"
RELEASE_STAGE_EVENT_KIND_ENUM = "release_stage_event_kind"
RELEASE_CONSUMER_OUTCOME_ENUM = "release_consumer_outcome"


class TrustedIssuerKey(PychestratePhase1Base, SerializableModel):
    """
        Public Ed25519 keys the verifier accepts. M1 inserts
        the active key at bootstrap; M2 rotates by inserting a
        successor with ``replaced_by`` chained to the prior
        row.
    """

    __tablename__ = "release_trusted_issuer_keys"

    issuer_key_id = Column(String(128), primary_key=True)
    public_key_bytes = Column(LargeBinary, nullable=False)
    valid_from = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    valid_until = Column(UtcDateTime(timezone=True), nullable=True)
    replaced_by = Column(String(128), nullable=True)


class ReleaseRow(PychestratePhase1Base, SerializableModel):
    """
        Persistent row for a published release. The combination
        ``(component, version, channel)`` is unique.
    """

    __tablename__ = "release_releases"

    release_id = Column(UUIDType(binary=False), primary_key=True)
    component = Column(
        Enum(ReleaseComponent, name=RELEASE_COMPONENT_ENUM),
        nullable=False,
    )
    version = Column(String(64), nullable=False)
    channel = Column(
        Enum(ReleaseChannel, name=RELEASE_CHANNEL_ENUM),
        nullable=False,
    )
    artifact_uri = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False)
    manifest_bytes = Column(LargeBinary, nullable=False)
    signature = Column(LargeBinary, nullable=False)
    issuer_key_id = Column(String(128), nullable=False)
    issued_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    issued_by = Column(UUIDType(binary=False), nullable=True)
    status = Column(
        Enum(ReleaseStatus, name=RELEASE_STATUS_ENUM),
        nullable=False,
        default=ReleaseStatus.ACTIVE,
    )
    rollout_fraction = Column(Float, nullable=False, default=0.0)
    stage_started_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    previous_release_id = Column(
        UUIDType(binary=False), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "component", "version", "channel",
            name="uq_release_releases_component_version_channel",
        ),
        Index(
            "ix_release_releases_component_channel_status",
            "component", "channel", "status",
        ),
        Index(
            "ix_release_releases_issued_at",
            "issued_at",
        ),
    )


class ChannelStateRow(PychestratePhase1Base, SerializableModel):
    """
        Authoritative pointer for "which release is currently
        advertised on channel X for component Y".
    """

    __tablename__ = "release_channel_state"

    component = Column(
        Enum(ReleaseComponent, name=RELEASE_COMPONENT_ENUM),
        primary_key=True,
    )
    channel = Column(
        Enum(ReleaseChannel, name=RELEASE_CHANNEL_ENUM),
        primary_key=True,
    )
    current_release_id = Column(
        UUIDType(binary=False), nullable=True,
    )
    previous_release_id = Column(
        UUIDType(binary=False), nullable=True,
    )
    last_promotion_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_rollback_at = Column(UtcDateTime(timezone=True), nullable=True)


class ReleaseStageEvent(PychestratePhase1Base, SerializableModel):
    """
        Append-only ledger row for every stage transition.
    """

    __tablename__ = "release_stage_events"

    event_id = Column(UUIDType(binary=False), primary_key=True)
    release_id = Column(
        UUIDType(binary=False),
        ForeignKey("release_releases.release_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(
        Enum(StageEventKind, name=RELEASE_STAGE_EVENT_KIND_ENUM),
        nullable=False,
    )
    from_fraction = Column(Float, nullable=True)
    to_fraction = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    actor_user_id = Column(UUIDType(binary=False), nullable=True)
    occurred_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        Index(
            "ix_release_stage_events_release_occurred",
            "release_id", "occurred_at",
        ),
    )


class ConsumerOutcomeRow(PychestratePhase1Base, SerializableModel):
    """
        Per-consumer outcome rolled up at the release level.
    """

    __tablename__ = "release_consumer_outcomes"

    release_id = Column(
        UUIDType(binary=False),
        ForeignKey("release_releases.release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    consumer_id = Column(String(128), primary_key=True)
    component = Column(
        Enum(ReleaseComponent, name=RELEASE_COMPONENT_ENUM),
        nullable=False,
    )
    outcome = Column(
        Enum(ConsumerOutcome, name=RELEASE_CONSUMER_OUTCOME_ENUM),
        nullable=False,
    )
    reason = Column(Text, nullable=True)
    reported_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        Index(
            "ix_release_consumer_outcomes_release_outcome",
            "release_id", "outcome", "reported_at",
        ),
    )
