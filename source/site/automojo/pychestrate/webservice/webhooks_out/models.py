"""
.. module:: webhooks_out.models
    :synopsis: SQLAlchemy models + enums for outbound webhooks.
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
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class DeliveryOutcome(str, enum.Enum):
    """
        Outcome of one delivery attempt. M1 records whatever
        the caller (M2 dispatcher) reports; the enum captures
        the canonical bucketing.
    """
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED_DISABLED = "rejected_disabled"


class SignatureScheme(str, enum.Enum):
    """
        Signing scheme persisted on the target row.
    """
    HMAC_SHA256 = "hmac_sha256"


WEBHOOK_DELIVERY_OUTCOME_ENUM = "webhook_out_delivery_outcome"
WEBHOOK_SIGNATURE_SCHEME_ENUM = "webhook_out_signature_scheme"


class WebhookTarget(PychestratePhase1Base, SerializableModel):
    """
        Per-(project, name) outbound webhook configuration.
    """

    __tablename__ = "webhooks_out_target"

    target_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="")
    url = Column(Text, nullable=False)
    secret_ref = Column(Text, nullable=False, default="")
    signature_scheme = Column(
        Enum(SignatureScheme, name=WEBHOOK_SIGNATURE_SCHEME_ENUM),
        nullable=False,
        default=SignatureScheme.HMAC_SHA256,
    )
    topic_filters = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    custom_headers = Column(JSON, nullable=False, default=dict)
    created_by = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "name",
            name="uq_webhooks_out_target_project_name",
        ),
        Index("ix_webhooks_out_target_project_enabled", "project_id", "enabled"),
    )


class WebhookDelivery(PychestratePhase1Base, SerializableModel):
    """
        Per-attempt delivery row.
    """

    __tablename__ = "webhooks_out_delivery"

    delivery_id = Column(UUIDType(binary=False), primary_key=True)
    target_id = Column(
        UUIDType(binary=False),
        ForeignKey("webhooks_out_target.target_id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(UUIDType(binary=False), nullable=False)
    topic = Column(String(128), nullable=False, default="")
    payload_digest_sha256 = Column(String(64), nullable=False, default="")
    signature = Column(Text, nullable=False, default="")
    request_headers = Column(JSON, nullable=False, default=dict)
    outcome = Column(
        Enum(DeliveryOutcome, name=WEBHOOK_DELIVERY_OUTCOME_ENUM),
        nullable=False,
        default=DeliveryOutcome.PENDING,
    )
    response_status = Column(Integer, nullable=True)
    response_excerpt = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    attempted_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_webhooks_out_delivery_target_attempted",
            "target_id", "attempted_at",
        ),
        Index(
            "ix_webhooks_out_delivery_outcome",
            "outcome",
        ),
    )
