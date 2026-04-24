"""
.. module:: tagging.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 2-tagging feature.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class TagAssignment(PychestratePhase1Base, SerializableModel):
    """
        A single (entity_kind, entity_id, taxonomy, value) tuple.
    """

    __tablename__ = "tagging_tag_assignments"

    assignment_id = Column(UUIDType(binary=False), primary_key=True)
    entity_kind = Column(String(32), nullable=False)
    entity_id = Column(UUIDType(binary=False), nullable=False)
    taxonomy_name = Column(String(32), nullable=False)
    canonical_value = Column(String(256), nullable=False)
    assigned_by_user_id = Column(UUIDType(binary=False), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "entity_kind", "entity_id", "taxonomy_name", "canonical_value",
            name="uq_tagging_assignment_scope",
        ),
        Index("ix_tagging_assignment_entity", "entity_kind", "entity_id"),
        Index("ix_tagging_assignment_taxonomy", "taxonomy_name", "canonical_value"),
    )
