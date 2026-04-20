"""
.. module:: identity.users.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-user-management feature.

.. moduleauthor:: Automation Mojo LLC

These models live in a dedicated spec-shaped schema for the Phase 1
identity rebuild; they coexist with the legacy ``users`` table owned by
``automojo.pychestrate.core.orm.User`` until the cut-over lands.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class UserStatus(enum.Enum):
    """
        Status of a user record in the identity store.
    """
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"
    PENDING = "PENDING"


class IdentityUser(PychestratePhase1Base, SerializableModel):
    """
        Canonical identity record. Keyed by a server-generated UUID so that
        external directory renames never break foreign keys.
    """

    __tablename__ = "identity_users"

    user_id = Column(UUIDType(binary=False), primary_key=True)
    login_name = Column(String(128), nullable=False, unique=True)
    primary_email = Column(String(320), nullable=False, unique=True)
    display_name = Column(String(256), nullable=False, default="")
    status = Column(
        Enum(UserStatus, name="identity_user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    provisioning_source = Column(String(128), nullable=False, default="local")
    external_id = Column(String(256), nullable=True)
    timezone = Column(String(64), nullable=False, default="UTC")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "provisioning_source", "external_id",
            name="uq_identity_users_provisioning_external",
        ),
        Index("ix_identity_users_status", "status"),
    )


class IdentityGroup(PychestratePhase1Base, SerializableModel):
    """
        Named collection of users for RBAC binding attachment.
    """

    __tablename__ = "identity_groups"

    group_id = Column(UUIDType(binary=False), primary_key=True)
    group_name = Column(String(128), nullable=False, unique=True)
    description = Column(String(512), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class IdentityGroupMembership(PychestratePhase1Base, SerializableModel):
    """
        Join row between :class:`IdentityGroup` and :class:`IdentityUser`.
    """

    __tablename__ = "identity_group_memberships"

    group_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_groups.group_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    added_by = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )


class IdentityEmailVerification(PychestratePhase1Base, SerializableModel):
    """
        Pending email-change verification row. Consumed by M2 flow.
    """

    __tablename__ = "identity_email_verifications"

    verification_id = Column(UUIDType(binary=False), primary_key=True)
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    new_email = Column(String(320), nullable=False)
    token_hash = Column(LargeBinary(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
