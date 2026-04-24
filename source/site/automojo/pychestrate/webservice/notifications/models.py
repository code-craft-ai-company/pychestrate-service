"""
.. module:: notifications.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-notification-hub feature.

.. moduleauthor:: Automation Mojo LLC
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

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


_JsonPayload = JSON().with_variant(JSONB(), "postgresql")


class ChannelScopeLevel(enum.Enum):
    """
        Whether the channel is system-wide or project-scoped.
    """
    SYSTEM = "SYSTEM"
    PROJECT = "PROJECT"


class DispatchOutcome(enum.Enum):
    """
        Result of a single dispatch attempt.
    """
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEFERRED = "DEFERRED"


class NotificationChannel(PychestratePhase1Base, SerializableModel):
    """
        An addressable delivery endpoint (SMTP / Slack / webhook / ...).
    """

    __tablename__ = "notifications_channels"

    channel_id = Column(UUIDType(binary=False), primary_key=True)
    name = Column(String(128), nullable=False)
    kind = Column(String(32), nullable=False)
    scope_level = Column(
        Enum(ChannelScopeLevel, name="notifications_scope_level"),
        nullable=False,
    )
    project_id = Column(UUIDType(binary=False), nullable=True)
    config = Column(_JsonPayload, nullable=False, default=dict)
    disabled = Column(Boolean(), nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "scope_level", "project_id", "name",
            name="uq_notifications_channels_name",
        ),
        Index("ix_notifications_channels_kind", "kind"),
    )


class NotificationRoutingRule(PychestratePhase1Base, SerializableModel):
    """
        A routing rule binding a project event pattern to channels.
    """

    __tablename__ = "notifications_routing_rules"

    rule_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=True)
    event_pattern = Column(String(128), nullable=False)
    filter_tag_expression = Column(String(512), nullable=True)
    recipients = Column(_JsonPayload, nullable=False, default=list)
    channel_ids = Column(_JsonPayload, nullable=False, default=list)
    template_name = Column(String(128), nullable=False)
    rate_limit_per_minute = Column(Integer(), nullable=True)
    disabled = Column(Boolean(), nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_notifications_routing_project", "project_id"),
        Index("ix_notifications_routing_pattern", "event_pattern"),
    )


class NotificationDispatchEnvelope(PychestratePhase1Base, SerializableModel):
    """
        Single dispatch record — one row per recipient/channel pair.
    """

    __tablename__ = "notifications_dispatch_envelopes"

    envelope_id = Column(UUIDType(binary=False), primary_key=True)
    event_topic = Column(String(128), nullable=False)
    recipient = Column(String(320), nullable=False)
    channel_id = Column(
        UUIDType(binary=False),
        ForeignKey("notifications_channels.channel_id", ondelete="CASCADE"),
        nullable=False,
    )
    template_name = Column(String(128), nullable=False)
    severity = Column(String(16), nullable=False, default="INFO")
    rendered_subject = Column(String(512), nullable=False, default="")
    rendered_body = Column(Text(), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_notifications_dispatch_channel", "channel_id"),
        Index("ix_notifications_dispatch_topic", "event_topic"),
    )


class UserNotificationPreferences(PychestratePhase1Base, SerializableModel):
    """
        Per-user notification preferences + quiet-hours window.
    """

    __tablename__ = "notifications_user_preferences"

    user_id = Column(UUIDType(binary=False), primary_key=True)
    topics_enabled = Column(_JsonPayload, nullable=False, default=dict)
    quiet_hours = Column(_JsonPayload, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class NotificationDeadLetter(PychestratePhase1Base, SerializableModel):
    """
        Terminal failure rows parked for replay or inspection.
    """

    __tablename__ = "notifications_dead_letters"

    envelope_id = Column(
        UUIDType(binary=False),
        ForeignKey(
            "notifications_dispatch_envelopes.envelope_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    last_error = Column(Text(), nullable=False, default="")
    attempt_count = Column(Integer(), nullable=False, default=0)
    replayable = Column(Boolean(), nullable=False, default=True)
    parked_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class NotificationDispatchAttempt(PychestratePhase1Base, SerializableModel):
    """
        One delivery attempt against a :class:`NotificationDispatchEnvelope`.
    """

    __tablename__ = "notifications_dispatch_attempts"

    attempt_id = Column(UUIDType(binary=False), primary_key=True)
    envelope_id = Column(
        UUIDType(binary=False),
        ForeignKey(
            "notifications_dispatch_envelopes.envelope_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    attempt_number = Column(Integer(), nullable=False, default=1)
    outcome = Column(
        Enum(DispatchOutcome, name="notifications_dispatch_outcome"),
        nullable=False,
    )
    error_message = Column(Text(), nullable=True)
    latency_ms = Column(Integer(), nullable=True)
    attempted_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_notifications_attempts_envelope", "envelope_id"),
    )
