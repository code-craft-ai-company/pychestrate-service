"""
.. module:: resources.pools.models
    :synopsis: SQLAlchemy models for resource pools.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ResourcePool(PychestratePhase1Base, SerializableModel):
    """
        Capability-tagged grouping of resources.
    """

    __tablename__ = "resources_resource_pool"

    pool_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False, default="")
    description = Column(String(1024), nullable=False, default="")
    capability_tags = Column(JSON, nullable=False, default=list)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "name",
            name="uq_resources_resource_pool_project_name",
        ),
        Index("ix_resources_resource_pool_project", "project_id"),
    )


class ResourcePoolMember(PychestratePhase1Base, SerializableModel):
    """
        Resource-to-pool membership row. UNIQUE on
        ``(pool_id, resource_id)`` so a resource is at most a
        single member of any given pool.
    """

    __tablename__ = "resources_resource_pool_member"

    membership_id = Column(UUIDType(binary=False), primary_key=True)
    pool_id = Column(
        UUIDType(binary=False),
        ForeignKey("resources_resource_pool.pool_id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id = Column(UUIDType(binary=False), nullable=False)
    added_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "pool_id", "resource_id",
            name="uq_resources_resource_pool_member_pool_resource",
        ),
        Index("ix_resources_resource_pool_member_resource", "resource_id"),
    )
