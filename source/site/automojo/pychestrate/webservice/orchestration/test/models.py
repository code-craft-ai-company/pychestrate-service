"""
.. module:: orchestration.test.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for the test-run row.

.. moduleauthor:: Automation Mojo LLC

The ``orchestration_test_run`` row tracks orchestration-level
state (``triggered``, ``dispatching``, ``dispatched``, terminal
buckets). It is *separate* from the run-state-machine row owned
by ``5-run-state-machine``: the former is the orchestration's
view of the trigger flow, the latter is the dispatch / receipt /
progress / result lifecycle. The two are linked by ``run_id``.
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
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class TestRunState(str, enum.Enum):
    """
        Orchestration-level lifecycle for a test run.
    """
    TRIGGERED = "triggered"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    DISPATCH_FAILED = "dispatch_failed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INVESTIGATION = "needs_investigation"
    INELIGIBLE = "ineligible"


TEST_RUN_STATE_ENUM = "orchestration_test_run_state"


class TestRun(PychestratePhase1Base, SerializableModel):
    """
        One row per orchestration trigger. ``run_id`` links the
        row to the ``runs_run`` row owned by the run-state-machine.
    """

    __tablename__ = "orchestration_test_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    catalog_entry_id = Column(UUIDType(binary=False), nullable=False)
    runner_kind = Column(String(64), nullable=False, default="")
    triggered_by = Column(UUIDType(binary=False), nullable=True)
    state = Column(
        Enum(TestRunState, name=TEST_RUN_STATE_ENUM),
        nullable=False,
        default=TestRunState.TRIGGERED,
    )
    triggered_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    dispatch_attempt_id = Column(UUIDType(binary=False), nullable=True)
    failure_reason = Column(Text, nullable=True)
    inputs_json = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_orchestration_test_run_project", "project_id"),
        Index("ix_orchestration_test_run_state", "state"),
        Index("ix_orchestration_test_run_catalog_entry", "catalog_entry_id"),
    )
