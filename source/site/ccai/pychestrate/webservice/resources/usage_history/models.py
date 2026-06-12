"""
.. module:: resources.usage_history.models
    :synopsis: SQLAlchemy model + enum for resource timeline rows.
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
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class UsageEventType(str, enum.Enum):
    """
        Bounded set of timeline-event types covered by M1.

        The string values mirror the originating bus topic so
        downstream consumers can pivot the timeline back into
        the bus stream without a translation table. M2 widens
        this enum as new resource events graduate from internal
        signals to first-class timeline rows.
    """
    RESOURCE_REGISTERED = "resource.registered"
    RESOURCE_QUARANTINED = "resource.quarantined"
    RESOURCE_UNQUARANTINED = "resource.unquarantined"
    RESOURCE_RETIRED = "resource.retired"
    RESERVATION_GRANTED = "reservation.granted"
    RESERVATION_RELEASED = "reservation.released"
    RESERVATION_FORCED_RELEASED = "reservation.forced_released"
    RESERVATION_REJECTED = "reservation.conflict_rejected"
    LEASE_ATTACHED = "lease.attached"
    LEASE_RENEWED = "lease.renewed"
    LEASE_EXPIRED = "lease.expired"
    HEALTH_PROBED = "health.probed"


USAGE_EVENT_TYPE_ENUM = "resources_usage_event_type"


class ResourceTimelineEvent(PychestratePhase1Base, SerializableModel):
    """
        Append-only timeline event for a resource. ``event_id``
        is the primary key; the
        ``(source_event_id, resource_id)`` UNIQUE makes
        :func:`append_event` safely re-runnable when a bus
        subscriber retries delivery.
    """

    __tablename__ = "resources_timeline_event"

    event_id = Column(UUIDType(binary=False), primary_key=True)
    source_event_id = Column(UUIDType(binary=False), nullable=False)
    resource_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    event_type = Column(
        Enum(UsageEventType, name=USAGE_EVENT_TYPE_ENUM),
        nullable=False,
    )
    actor_id = Column(UUIDType(binary=False), nullable=True)
    pod_event_group_id = Column(UUIDType(binary=False), nullable=True)
    at_ts = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload = Column(JSON, nullable=False, default=dict)
    annotations = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "source_event_id", "resource_id",
            name="uq_resources_timeline_event_source_resource",
        ),
        Index(
            "ix_resources_timeline_event_resource_at",
            "resource_id", "at_ts",
        ),
        Index(
            "ix_resources_timeline_event_type_at",
            "event_type", "at_ts",
        ),
        Index(
            "ix_resources_timeline_event_pod_group",
            "pod_event_group_id",
        ),
    )
