"""
.. module:: orchestration.infra.guards.models
    :synopsis: SQLAlchemy model for guard attachments.

The two-person review ledger lands in M2; M1 ships only the
per-environment rule attachment row.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
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

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


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
    added_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
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
