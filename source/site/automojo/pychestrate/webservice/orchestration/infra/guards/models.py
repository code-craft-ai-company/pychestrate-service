"""
.. module:: orchestration.infra.guards.models
    :synopsis: SQLAlchemy model for guard attachments.

The two-person review ledger lands in M2; M1 ships only the
per-environment rule attachment row.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class GuardAttachment(PychestratePhase1Base, SerializableModel):
    """
        Per-(project, environment, rule) attachment row.
    """

    __tablename__ = "orch_guard_attachment"

    project_id = Column(UUIDType(binary=False), nullable=False)
    environment_id = Column(UUIDType(binary=False), nullable=False)
    rule_id = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    added_by = Column(UUIDType(binary=False), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "environment_id", "rule_id",
            name="pk_orch_guard_attachment",
        ),
        Index(
            "ix_orch_guard_attachment_env_enabled",
            "environment_id", "enabled",
        ),
    )
