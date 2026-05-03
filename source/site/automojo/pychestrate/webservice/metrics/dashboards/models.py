"""
.. module:: metrics.dashboards.models
    :synopsis: SQLAlchemy model for project dashboards.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class Dashboard(PychestratePhase1Base, SerializableModel):
    """
        One per-project dashboard. Tiles persist inline as
        JSON for M1; the M2 reflow + audit-diff path keeps the
        same schema.
    """

    __tablename__ = "metrics_dashboard"

    dashboard_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="")
    owner_principal_id = Column(UUIDType(binary=False), nullable=True)
    grid_columns_max = Column(Integer, nullable=False, default=12)
    tiles = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_dashboard_project_name",
        ),
        Index("ix_metrics_dashboard_project", "project_id"),
    )
