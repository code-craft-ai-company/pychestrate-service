"""
.. module:: jobs.offline.models
    :synopsis: SQLAlchemy models for offline tolerance.
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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class PodLivenessTier(str, enum.Enum):
    """
        Three-tier liveness classification driven by drop +
        reconnect events.
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


POD_LIVENESS_TIER_ENUM = "jobs_offline_pod_liveness_tier"


class DeferredCancelStatus(str, enum.Enum):
    """
        Lifecycle of a queued cancel request.
    """
    QUEUED = "queued"
    DELIVERED = "delivered"
    EXPIRED = "expired"


DEFERRED_CANCEL_STATUS_ENUM = "jobs_offline_deferred_cancel_status"


class PodOfflineState(PychestratePhase1Base, SerializableModel):
    """
        One row per pod tracking its current liveness tier and
        the timestamps the offline service uses to expire
        deferred cancels.
    """

    __tablename__ = "jobs_pod_offline_state"

    pod_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    tier = Column(
        Enum(PodLivenessTier, name=POD_LIVENESS_TIER_ENUM),
        nullable=False,
        default=PodLivenessTier.HEALTHY,
    )
    last_session_dropped_at = Column(DateTime(timezone=True), nullable=True)
    last_reconnected_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_jobs_pod_offline_state_tier", "tier"),
    )


class ClientReplayCursor(PychestratePhase1Base, SerializableModel):
    """
        Monotonic cursor per ``(client_id, run_id)`` tracking the
        next replay sequence the service expects.
    """

    __tablename__ = "jobs_client_replay_cursor"

    cursor_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(UUIDType(binary=False), nullable=False)
    run_id = Column(UUIDType(binary=False), nullable=False)
    next_expected_sequence = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "client_id", "run_id",
            name="uq_jobs_client_replay_cursor_client_run",
        ),
    )


class DeferredCancel(PychestratePhase1Base, SerializableModel):
    """
        One row per queued cancel request awaiting client
        reconnect.
    """

    __tablename__ = "jobs_deferred_cancel"

    deferred_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    pod_id = Column(UUIDType(binary=False), nullable=False)
    cancel_request_id = Column(UUIDType(binary=False), nullable=False)
    reason = Column(String(512), nullable=False, default="")
    status = Column(
        Enum(DeferredCancelStatus, name=DEFERRED_CANCEL_STATUS_ENUM),
        nullable=False,
        default=DeferredCancelStatus.QUEUED,
    )
    queued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_jobs_deferred_cancel_pod", "pod_id"),
        Index("ix_jobs_deferred_cancel_status", "status"),
        Index("ix_jobs_deferred_cancel_run", "run_id"),
    )
