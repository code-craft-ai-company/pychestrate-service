"""
.. module:: jobs.reconcile.models
    :synopsis: SQLAlchemy model for reconcile_decision.
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
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ReconcileOutcome(str, enum.Enum):
    """
        Classification of a reconciler decision.
    """
    NO_CHANGE = "no_change"
    DIVERGENCE_RESOLVED = "divergence_resolved"
    PROGRESS_RESUMED = "progress_resumed"
    NEEDS_INVESTIGATION = "needs_investigation"


RECONCILE_OUTCOME_ENUM = "jobs_reconcile_outcome"


class ReconcileDecision(PychestratePhase1Base, SerializableModel):
    """
        One row per reconcile pass against a run.
    """

    __tablename__ = "jobs_reconcile_decision"

    decision_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    prior_state = Column(String(64), nullable=False, default="")
    resolved_state = Column(String(64), nullable=False, default="")
    outcome = Column(
        Enum(ReconcileOutcome, name=RECONCILE_OUTCOME_ENUM),
        nullable=False,
        default=ReconcileOutcome.NO_CHANGE,
    )
    source = Column(String(64), nullable=False, default="client_truth")
    note = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_jobs_reconcile_decision_run", "run_id"),
        Index("ix_jobs_reconcile_decision_outcome", "outcome"),
    )
