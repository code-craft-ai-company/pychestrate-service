"""
.. module:: metrics.alerts.models
    :synopsis: SQLAlchemy models + enums for alert rules / live state.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class AlertSeverity(str, enum.Enum):
    """
        Severity bucket assigned to an alert rule.
    """
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(str, enum.Enum):
    """
        Current state of the alert.

        ``OK`` — last evaluation passed; ``FIRING`` — last
        evaluation failed; ``UNKNOWN`` — never evaluated.
    """
    UNKNOWN = "unknown"
    OK = "ok"
    FIRING = "firing"


ALERT_SEVERITY_ENUM = "metrics_alert_severity"
ALERT_STATE_ENUM = "metrics_alert_state"


class AlertRule(PychestratePhase1Base, SerializableModel):
    """
        Per-project alert rule.
    """

    __tablename__ = "metrics_alert_rule"

    rule_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="")
    kind = Column(String(64), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    severity = Column(
        Enum(AlertSeverity, name=ALERT_SEVERITY_ENUM),
        nullable=False,
        default=AlertSeverity.WARNING,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    notification_targets = Column(JSON, nullable=False, default=list)
    created_by = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_alert_rule_project_name",
        ),
        Index("ix_metrics_alert_rule_project_enabled", "project_id", "enabled"),
        Index("ix_metrics_alert_rule_kind", "kind"),
    )


class AlertLiveState(PychestratePhase1Base, SerializableModel):
    """
        Per-rule live state surfaced after each evaluation.
    """

    __tablename__ = "metrics_alert_live_state"

    rule_id = Column(
        UUIDType(binary=False),
        ForeignKey("metrics_alert_rule.rule_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state = Column(
        Enum(AlertState, name=ALERT_STATE_ENUM),
        nullable=False,
        default=AlertState.UNKNOWN,
    )
    last_value = Column(JSON, nullable=True)
    last_threshold = Column(JSON, nullable=True)
    last_reason = Column(Text, nullable=False, default="")
    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    last_state_changed_at = Column(DateTime(timezone=True), nullable=True)
    fired_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    fire_count = Column(Integer, nullable=False, default=0)
    resolve_count = Column(Integer, nullable=False, default=0)
