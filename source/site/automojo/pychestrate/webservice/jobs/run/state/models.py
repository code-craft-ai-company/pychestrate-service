"""
.. module:: jobs.run.state.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for run / run_state_audit / run_event_outbox.

.. moduleauthor:: Automation Mojo LLC

Three tables land in migration ``017_phase3_run_state``:

- ``runs_run`` — one row per run, authoritative state + bookkeeping.
- ``runs_run_state_audit`` — append-only audit log of every transition.
- ``runs_run_event_outbox`` — durable outbox row per milestone event.
  The in-process bus publisher also runs against the session's
  ``messaging.outbox`` so publishing is near-immediate; the outbox
  table exists so a crash between state commit and bus publish does
  not lose the event — a restart daemon (M2) drains the table.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TerminalOutcome,
)
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


RUN_STATE_ENUM = "runs_run_state"
RUN_EVENT_ENUM = "runs_run_event"
TERMINAL_OUTCOME_ENUM = "runs_terminal_outcome"


class Run(PychestratePhase1Base, SerializableModel):
    """
        Authoritative run row. Owned by the state machine — every
        other feature reads, but only the state machine writes.
    """

    __tablename__ = "runs_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    job_type = Column(String(64), nullable=False, default="")
    state = Column(
        Enum(RunState, name=RUN_STATE_ENUM),
        nullable=False,
        default=RunState.PENDING,
    )
    prior_state = Column(
        Enum(RunState, name=RUN_STATE_ENUM),
        nullable=True,
    )
    entered_state_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    progress_last_observed_at = Column(DateTime(timezone=True), nullable=True)
    terminal_outcome = Column(
        Enum(TerminalOutcome, name=TERMINAL_OUTCOME_ENUM),
        nullable=True,
    )
    cancel_reason = Column(String(512), nullable=True)
    cancel_actor = Column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_runs_run_project_state", "project_id", "state"),
        Index("ix_runs_run_state_progress", "state", "progress_last_observed_at"),
    )


class RunStateAudit(PychestratePhase1Base, SerializableModel):
    """
        Append-only audit record of every transition. Kept separate
        from the ``run`` row so historical investigation has full
        fidelity even after rotations.
    """

    __tablename__ = "runs_run_state_audit"

    audit_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(
        UUIDType(binary=False),
        ForeignKey("runs_run.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_state = Column(Enum(RunState, name=RUN_STATE_ENUM), nullable=False)
    to_state = Column(Enum(RunState, name=RUN_STATE_ENUM), nullable=False)
    event = Column(Enum(RunEvent, name=RUN_EVENT_ENUM), nullable=False)
    actor = Column(String(256), nullable=False, default="")
    reason = Column(Text, nullable=True)
    transitioned_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_runs_run_state_audit_run_id", "run_id"),
        Index("ix_runs_run_state_audit_transitioned_at", "transitioned_at"),
    )


class RunEventOutbox(PychestratePhase1Base, SerializableModel):
    """
        Durable outbox row — one per milestone bus event emitted by
        the state machine. Written in the same transaction as the
        ``run`` UPDATE + ``run_state_audit`` INSERT. The bus publisher
        (in-process ``messaging.outbox`` for synchronous delivery,
        plus an offline drainer daemon for crash recovery) reads from
        here.
    """

    __tablename__ = "runs_run_event_outbox"

    outbox_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    topic = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    published_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_runs_run_event_outbox_run_id", "run_id"),
        Index("ix_runs_run_event_outbox_published_at", "published_at"),
    )
