"""
.. module:: variables.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-global-variables feature.

.. moduleauthor:: Automation Mojo LLC
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
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


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
    set_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "scope", "scope_id", "name",
            name="uq_variables_scope_name",
        ),
        Index("ix_variables_scope", "scope"),
        Index("ix_variables_scope_scope_id", "scope", "scope_id"),
    )
