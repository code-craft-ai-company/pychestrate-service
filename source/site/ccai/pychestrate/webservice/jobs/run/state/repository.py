"""
.. module:: jobs.run.state.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for Run / RunStateAudit / RunEventOutbox.

.. moduleauthor:: Code Craft AI LLC

Thin wrappers around SQLAlchemy so the machine's call sites stay
readable. Callers own the transaction boundary — the machine opens
and commits inside :meth:`RunStateMachine.transition` so one Postgres
transaction covers the UPDATE + INSERT + OUTBOX INSERT chain.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TerminalOutcome,
)
from ccai.pychestrate.webservice.jobs.run.state.errors import (
    RunNotFoundError,
)
from ccai.pychestrate.webservice.jobs.run.state.models import (
    Run,
    RunEventOutbox,
    RunStateAudit,
)


def create_run(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        job_type: str,
        initial_state: RunState = RunState.PENDING,
        entered_at: Optional[datetime] = None
    ) -> Run:
    """
        Insert a fresh run row in the given initial state.

        :param db_session: Active SQLAlchemy session.
        :param run_id: UUID string assigned upstream (envelope /
                       dispatcher typically own this).
        :param project_id: Owning project UUID.
        :param job_type: Job-type string for downstream routing.
        :param initial_state: Starting state — defaults to
                              :attr:`RunState.PENDING`.
        :param entered_at: Optional timestamp (tests pass a fixed
                           value); defaults to the column's
                           server-side ``utc_now`` default.

        :returns: The persisted :class:`Run` row (flushed; not
                  committed).
    """
    row = Run(
        run_id=run_id,
        project_id=project_id,
        job_type=job_type,
        state=initial_state,
        prior_state=None,
    )
    if entered_at is not None:
        row.entered_state_at = entered_at
    db_session.add(row)
    db_session.flush()
    return row


def get_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Run:
    """
        Fetch a run row by id. Raises when no row exists so callers
        never silently work against ``None``.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: The :class:`Run` row.
        :raises: RunNotFoundError.
    """
    row = db_session.query(Run).filter(Run.run_id == run_id).first()
    if row is None:
        err_lines = ["Run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise RunNotFoundError(err_msg) from None
    return row


def find_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[Run]:
    """
        Fetch a run row by id, returning ``None`` when missing. Used
        in paths where absence is not an error (e.g. the
        outbox-drainer's best-effort lookup).

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: The :class:`Run` row or ``None``.
    """
    rtnval = db_session.query(Run).filter(Run.run_id == run_id).first()
    return rtnval


def append_state_audit(
        *,
        db_session: DbSession,
        run_id: str,
        from_state: RunState,
        to_state: RunState,
        event: RunEvent,
        actor: str,
        reason: Optional[str],
        transitioned_at: datetime
    ) -> RunStateAudit:
    """
        Insert one :class:`RunStateAudit` row.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param from_state: State before the transition.
        :param to_state: State after the transition.
        :param event: Driving :class:`RunEvent`.
        :param actor: Actor string.
        :param reason: Optional free-form reason.
        :param transitioned_at: Commit timestamp.

        :returns: The persisted :class:`RunStateAudit` row.
    """
    row = RunStateAudit(
        audit_id=new_uuid(),
        run_id=run_id,
        from_state=from_state,
        to_state=to_state,
        event=event,
        actor=actor,
        reason=reason,
        transitioned_at=transitioned_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_state_audits(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[RunStateAudit]:
    """
        Return every audit row for a run ordered by
        ``transitioned_at``.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: List of :class:`RunStateAudit` rows (possibly
                  empty).
    """
    rows = (
        db_session.query(RunStateAudit)
        .filter(RunStateAudit.run_id == run_id)
        .order_by(RunStateAudit.transitioned_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def append_outbox_row(
        *,
        db_session: DbSession,
        run_id: str,
        topic: str,
        payload: dict,
        created_at: datetime
    ) -> RunEventOutbox:
    """
        Insert one durable outbox row.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param topic: Bus topic string.
        :param payload: JSON-serializable payload body.
        :param created_at: Commit timestamp.

        :returns: The persisted :class:`RunEventOutbox` row.
    """
    row = RunEventOutbox(
        outbox_id=new_uuid(),
        run_id=run_id,
        topic=topic,
        payload=payload,
        created_at=created_at,
        published_at=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_latest_outbox_row_for_topic(
        *,
        db_session: DbSession,
        run_id: str,
        topic: str
    ) -> Optional[RunEventOutbox]:
    """
        Return the most recently created outbox row for one
        ``(run_id, topic)`` pair, or ``None`` when the run has
        never emitted on that topic. Used by the run read model to
        recall durable milestone payloads (e.g. the latest
        result-manifest event) after the fact.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param topic: Bus topic string.

        :returns: The newest :class:`RunEventOutbox` row or ``None``.
    """
    rtnval = (
        db_session.query(RunEventOutbox)
        .filter(RunEventOutbox.run_id == run_id)
        .filter(RunEventOutbox.topic == topic)
        .order_by(RunEventOutbox.created_at.desc())
        .first()
    )
    return rtnval


def mark_outbox_published(
        *,
        db_session: DbSession,
        outbox_ids: List[str],
        published_at: datetime
    ) -> int:
    """
        Set ``published_at`` on every outbox row whose id is in
        ``outbox_ids``. Returns the number of rows updated for the
        drainer's bookkeeping.

        :param db_session: Active SQLAlchemy session.
        :param outbox_ids: UUIDs of the outbox rows being marked.
        :param published_at: Commit timestamp.

        :returns: Count of updated rows.
    """
    if len(outbox_ids) == 0:
        return 0
    count = (
        db_session.query(RunEventOutbox)
        .filter(RunEventOutbox.outbox_id.in_(outbox_ids))
        .update({"published_at": published_at}, synchronize_session=False)
    )
    rtnval = int(count)
    return rtnval


def list_unpublished_outbox_rows(
        *,
        db_session: DbSession,
        limit: int = 256
    ) -> List[RunEventOutbox]:
    """
        Return the oldest ``limit`` outbox rows still awaiting
        publication. Used by the drainer at startup / on demand.

        :param db_session: Active SQLAlchemy session.
        :param limit: Max rows to return.

        :returns: List of :class:`RunEventOutbox` rows ordered by
                  ``created_at``.
    """
    rows = (
        db_session.query(RunEventOutbox)
        .filter(RunEventOutbox.published_at.is_(None))
        .order_by(RunEventOutbox.created_at.asc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
