"""
.. module:: resources.inventory.models
    :synopsis: SQLAlchemy model + state enum for resource rows.
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
    Index,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ResourceState(str, enum.Enum):
    """
        Lifecycle of a registered resource.
    """
    AVAILABLE = "available"
    LEASED = "leased"
    QUARANTINED = "quarantined"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


RESOURCE_STATE_ENUM = "resources_resource_state"


class Resource(PychestratePhase1Base, SerializableModel):
    """
        Authoritative resource row. ``identity_hash`` is the
        per-kind canonical identifier; uniqueness is enforced at
        the application level (M1) since Postgres-only partial
        unique indices don't translate to SQLite.
    """

    __tablename__ = "resources_resource"

    resource_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    kind = Column(String(64), nullable=False, default="")
    display_name = Column(String(256), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    identity_hash = Column(String(128), nullable=False, default="")
    state = Column(
        Enum(ResourceState, name=RESOURCE_STATE_ENUM),
        nullable=False,
        default=ResourceState.AVAILABLE,
    )
    tags = Column(JSON, nullable=False, default=list)
    attributes = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_resources_resource_kind_state", "kind", "state"),
        Index("ix_resources_resource_project", "project_id"),
        Index("ix_resources_resource_identity", "kind", "identity_hash"),
    )
