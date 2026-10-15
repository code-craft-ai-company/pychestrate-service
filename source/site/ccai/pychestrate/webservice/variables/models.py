"""
.. module:: variables.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-global-variables feature.

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
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class VariableScope(enum.Enum):
    """
        The scope chain honored by variable resolution at M1.

        Only ``SYSTEM`` and ``PROJECT`` are wired in M1; ``PIPELINE``
        and ``JOB`` arrive in M2 alongside the evaluator trace endpoint.
    """
    SYSTEM = "SYSTEM"
    PROJECT = "PROJECT"
    PIPELINE = "PIPELINE"
    JOB = "JOB"


class VariableValueType(enum.Enum):
    """
        Declared payload shape for a variable binding.
    """
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"
    SECRET_REF = "SECRET_REF"


class VariableBinding(PychestratePhase1Base, SerializableModel):
    """
        A single (scope, scope_id, name) → value binding.
    """

    __tablename__ = "variables_variable_bindings"

    binding_id = Column(UUIDType(binary=False), primary_key=True)
    scope = Column(
        Enum(VariableScope, name="variables_variable_scope"),
        nullable=False,
    )
    scope_id = Column(String(64), nullable=False, default="")
    name = Column(String(128), nullable=False)
    value_type = Column(
        Enum(VariableValueType, name="variables_value_type"),
        nullable=False,
    )
    value_text = Column(Text(), nullable=True)
    set_by_user_id = Column(UUIDType(binary=False), nullable=True)
    set_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    #: What the variable is for, in words (shown on the Admin Variables pages; empty for one set through the API without it).
    description = Column(String(512), nullable=True)

    #: The value to fall back to, encoded like ``value_text`` (the Admin pages' "default value"); ``None`` when there is none.
    default_value_text = Column(Text(), nullable=True)

    #: When the binding was first created (``set_at`` is the last change); ``None`` for a row older than this column.
    created_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "scope", "scope_id", "name",
            name="uq_variables_scope_name",
        ),
        Index("ix_variables_scope", "scope"),
        Index("ix_variables_scope_scope_id", "scope", "scope_id"),
    )


class VariableBindingHistory(PychestratePhase1Base, SerializableModel):
    """
        One change to a variable: it was set (``old_value_text`` is ``None`` for the first time) or removed (``new_value_text`` is ``None``).
        Written by :func:`variables.service.set_variable` and :func:`variables.service.unset_variable` in the same transaction as the binding, so every
        way of changing a variable (the Admin pages, the REST API, the interface profile) is in the history. It survives the binding.
    """

    __tablename__ = "variables_binding_history"

    history_id = Column(UUIDType(binary=False), primary_key=True)
    scope = Column(
        Enum(VariableScope, name="variables_variable_scope"),
        nullable=False,
    )
    scope_id = Column(String(64), nullable=False, default="")
    name = Column(String(128), nullable=False)
    value_type = Column(
        Enum(VariableValueType, name="variables_value_type"),
        nullable=False,
    )
    old_value_text = Column(Text(), nullable=True)
    new_value_text = Column(Text(), nullable=True)
    changed_by_user_id = Column(UUIDType(binary=False), nullable=True)
    changed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_variables_history_name", "scope", "scope_id", "name", "changed_at"),
    )
