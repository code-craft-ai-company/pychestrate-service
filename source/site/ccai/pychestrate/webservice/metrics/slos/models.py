"""
.. module:: metrics.slos.models
    :synopsis: SQLAlchemy models for SLO catalog + burn-rate state.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class SLO(PychestratePhase1Base, SerializableModel):
    """
        Per-project SLO definition.
    """

    __tablename__ = "metrics_slo"

    slo_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="")
    kind = Column(String(64), nullable=False)
    target = Column(Float, nullable=False, default=0.99)
    window_seconds = Column(Integer, nullable=False, default=2592000)
    definition_config = Column(JSON, nullable=False, default=dict)
    default_notification_route_key = Column(String(128), nullable=True)
    auto_attach_burn_rate_alerts = Column(
        Boolean, nullable=False, default=False,
    )
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_slo_project_name",
        ),
        Index("ix_metrics_slo_project", "project_id"),
        Index("ix_metrics_slo_kind", "kind"),
    )


class SLOBurnRateState(PychestratePhase1Base, SerializableModel):
    """
        Per-SLO burn-rate state surfaced after each evaluation.
        M1 records the latest fast / slow burn rates; the M2
        burn-rate evaluator + alert auto-attach reads these.
    """

    __tablename__ = "metrics_slo_burn_rate_state"

    slo_id = Column(
        UUIDType(binary=False),
        ForeignKey("metrics_slo.slo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_fast_burn_rate = Column(Float, nullable=False, default=0.0)
    last_slow_burn_rate = Column(Float, nullable=False, default=0.0)
    last_fast_over_since = Column(UtcDateTime(timezone=True), nullable=True)
    last_slow_over_since = Column(UtcDateTime(timezone=True), nullable=True)
    last_evaluated_at = Column(UtcDateTime(timezone=True), nullable=True)
