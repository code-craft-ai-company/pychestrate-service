"""
.. module:: projects.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-projects feature.

.. moduleauthor:: Code Craft AI LLC
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
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


_ExtensionFields = JSON().with_variant(JSONB(), "postgresql")


class ProjectState(enum.Enum):
    """
        Lifecycle state for a :class:`Project` row.
    """
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Project(PychestratePhase1Base, SerializableModel):
    """
        Root aggregate for a Pychestrate project.
    """

    __tablename__ = "projects_projects"

    project_id = Column(UUIDType(binary=False), primary_key=True)
    slug = Column(String(63), nullable=False, unique=True)
    display_name = Column(String(256), nullable=False, default="")
    description = Column(String(2048), nullable=False, default="")
    state = Column(
        Enum(ProjectState, name="projects_project_state"),
        nullable=False,
        default=ProjectState.ACTIVE,
    )
    owning_group_id = Column(UUIDType(binary=False), nullable=True)
    template_id = Column(String(128), nullable=True)
    template_version = Column(String(32), nullable=True)
    extension_fields = Column(_ExtensionFields, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_projects_projects_state", "state"),
        Index("ix_projects_projects_owning_group_id", "owning_group_id"),
    )


class ProjectMemberBinding(PychestratePhase1Base, SerializableModel):
    """
        Attachment of an identity user to a project with a role name.
    """

    __tablename__ = "projects_project_member_bindings"

    binding_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(
        UUIDType(binary=False),
        ForeignKey("projects_projects.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUIDType(binary=False), nullable=False)
    role_name = Column(String(64), nullable=False)
    added_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    added_by_user_id = Column(UUIDType(binary=False), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", "role_name",
            name="uq_projects_member_bindings_scope",
        ),
        Index("ix_projects_member_bindings_user", "user_id"),
    )
