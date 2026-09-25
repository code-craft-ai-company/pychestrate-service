"""
.. module:: security.rbac.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-rbac feature.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
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
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class RoleSource(enum.Enum):
    """
        Where this role was contributed from.
    """
    BUILTIN = "BUILTIN"
    EXTENSION = "EXTENSION"
    CUSTOM = "CUSTOM"


class PermissionSource(enum.Enum):
    """
        Where this permission was contributed from.
    """
    BUILTIN = "BUILTIN"
    EXTENSION = "EXTENSION"
    CUSTOM = "CUSTOM"


class PermissionEffect(enum.Enum):
    """
        Whether a role grants or explicitly denies a permission.
    """
    ALLOW = "ALLOW"
    DENY = "DENY"


class PrincipalKind(enum.Enum):
    """
        Entity kind that a binding is attached to.
    """
    USER = "USER"
    GROUP = "GROUP"


class BindingScope(enum.Enum):
    """
        Scope at which a binding takes effect.
    """
    SYSTEM = "SYSTEM"
    ORGANIZATION = "ORGANIZATION"
    PROJECT = "PROJECT"


class RbacRole(PychestratePhase1Base, SerializableModel):
    """
        Registered RBAC role.
    """

    __tablename__ = "rbac_roles"

    role_id = Column(UUIDType(binary=False), primary_key=True)
    role_name = Column(String(128), nullable=False, unique=True)
    source = Column(Enum(RoleSource, name="rbac_role_source"), nullable=False)
    source_name = Column(String(128), nullable=True)
    description = Column(String(512), nullable=False, default="")
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)


class RbacPermission(PychestratePhase1Base, SerializableModel):
    """
        Registered RBAC permission key.
    """

    __tablename__ = "rbac_permissions"

    permission_id = Column(UUIDType(binary=False), primary_key=True)
    permission_key = Column(String(256), nullable=False, unique=True)
    description = Column(String(512), nullable=False, default="")
    source = Column(Enum(PermissionSource, name="rbac_permission_source"), nullable=False)
    source_name = Column(String(128), nullable=True)


class RbacRolePermission(PychestratePhase1Base, SerializableModel):
    """
        Join row declaring which permission a role carries, with effect.
    """

    __tablename__ = "rbac_role_permissions"

    role_id = Column(
        UUIDType(binary=False),
        ForeignKey("rbac_roles.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_key = Column(String(256), primary_key=True)
    effect = Column(Enum(PermissionEffect, name="rbac_permission_effect"), nullable=False)


class RbacRoleBinding(PychestratePhase1Base, SerializableModel):
    """
        Live binding of a role to a principal at a scope.
    """

    __tablename__ = "rbac_role_bindings"

    binding_id = Column(UUIDType(binary=False), primary_key=True)
    role_id = Column(
        UUIDType(binary=False),
        ForeignKey("rbac_roles.role_id", ondelete="CASCADE"),
        nullable=False,
    )
    principal_kind = Column(Enum(PrincipalKind, name="rbac_principal_kind"), nullable=False)
    principal_id = Column(UUIDType(binary=False), nullable=False)
    scope_kind = Column(Enum(BindingScope, name="rbac_binding_scope"), nullable=False)
    scope_id = Column(UUIDType(binary=False), nullable=True)
    inherits_into_project = Column(Boolean, nullable=False, default=False)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "role_id", "principal_kind", "principal_id", "scope_kind", "scope_id",
            name="uq_rbac_role_bindings_assignment",
        ),
        Index("ix_rbac_role_bindings_principal", "principal_kind", "principal_id"),
        Index("ix_rbac_role_bindings_scope", "scope_kind", "scope_id"),
    )
