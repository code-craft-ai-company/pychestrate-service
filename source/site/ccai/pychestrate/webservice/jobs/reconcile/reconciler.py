"""
.. module:: jobs.reconcile.reconciler
    :synopsis: RunReconciler — align service state with client truth.

The reconciler is invoked by an ``entity.client.reconnected``
subscriber (M2 wiring). M1 ships ``reconcile_on_reconnect`` as a
direct callable so tests + early integration code can drive the
flow without the bus subscriber.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.reconcile.models import (
    ReconcileDecision,
    ReconcileOutcome,
)
from sqlalchemy import func

from ccai.pychestrate.webservice.jobs.cancel.client_cancel import (
    resolve_cancel_target_client,
)
from ccai.pychestrate.webservice.jobs.cancel.heartbeattransport import (
    acknowledge_client_cancellation,
)
from ccai.pychestrate.webservice.jobs.envelope.models import JobEnvelopeRecord
from ccai.pychestrate.webservice.jobs.run.state import (
    Run,
    RunEvent,
    RunState,
    TERMINAL_STATES,
    get_snapshot,
    is_terminal,
    reconcile as run_state_reconcile,
)
from ccai.pychestrate.webservice.jobs.run.state import transition as run_state_transition
from ccai.pychestrate.webservice.jobs.run.state.advance import advance_to_cancelled


#: Actor tag on the state-audit rows of runs the reconciler times out.
DEADLINE_ACTOR = "system:deadline"

#: Event that ends a run past its hard deadline, by the state it is stuck
#: in: never acknowledged -> the dispatch failed or was lost; acknowledged
#: or running -> the run failed. CANCEL_REQUESTED / CANCELLING end as
#: CANCELLED (see expire_overdue_runs); NEEDS_INVESTIGATION is left for a
#: person.
_DEADLINE_EVENT_BY_STATE = {
    RunState.PENDING: RunEvent.DISPATCH_ABORTED,
    RunState.DISPATCHING: RunEvent.DISPATCH_ABORTED,
    RunState.DISPATCH_UNCONFIRMED: RunEvent.RECEIPT_LOST,
    RunState.DISPATCHED: RunEvent.FAILURE_OBSERVED,
    RunState.RUNNING: RunEvent.FAILURE_OBSERVED,
    RunState.PROGRESS_STALLED: RunEvent.FAILURE_OBSERVED,
    RunState.COMPLETING: RunEvent.FAILURE_OBSERVED,
}
_CANCEL_STATES = frozenset({RunState.CANCEL_REQUESTED, RunState.CANCELLING})

_LOGGER = logging.getLogger("pychestrate.jobs.reconcile")


class RunReconciler:
    """
        Decision engine for client-reconnect reconciliation.
    """

    def scan_once(
            self,
            *,
            db_session: DbSession,
            now: Optional[datetime] = None
        ) -> int:
        """
            Periodic-tick entry point. Ends every run past its hard
            deadline (:meth:`expire_overdue_runs`), then counts the runs
            still in a non-terminal state -- the population the
            reconciler tracks.

            :param db_session: Active SQLAlchemy session.
            :param now: Evaluation time (tests); defaults to now.

            :returns: Count of non-terminal runs observed after expiry.
        """
        expired = self.expire_overdue_runs(db_session=db_session, now=now)
        if len(expired) > 0:
            _LOGGER.info("pychestrate.reconcile.deadline_expired count=%d runs=%s",
                         len(expired), ",".join(expired))
        terminal_members = list(TERMINAL_STATES)
        rows = (
            db_session.query(Run)
            .filter(~Run.state.in_(terminal_members))
            .all()
        )
        rtnval = len(rows)
        return rtnval

    def expire_overdue_runs(
            self,
            *,
            db_session: DbSession,
            now: Optional[datetime] = None
        ) -> List[str]:
        """
            End every non-terminal run whose hard deadline (the latest
            signed envelope's ``hard_deadline_at``) has passed. Without
            this nothing enforced the deadline: a run whose pod vanished,
            or whose cancel the pod never confirmed, stayed "dispatched"
            or "cancel_requested" -- and its cancel was re-sent on every
            heartbeat -- indefinitely (E2E-16).

            A run awaiting a cancel ends CANCELLED and its open cancel
            requests are closed; any other run ends via the event in
            :data:`_DEADLINE_EVENT_BY_STATE`. Runs with no envelope (never
            signed) and NEEDS_INVESTIGATION runs are left alone.

            :param db_session: Active SQLAlchemy session.
            :param now: Evaluation time (tests); defaults to now.

            :returns: The ids of the runs ended.
        """
        evaluated_at = now if now is not None else utc_now()
        latest_deadline = (
            db_session.query(
                JobEnvelopeRecord.run_id.label("run_id"),
                func.max(JobEnvelopeRecord.hard_deadline_at).label("hard_deadline_at"),
            )
            .group_by(JobEnvelopeRecord.run_id)
            .subquery()
        )
        overdue = (
            db_session.query(Run.run_id, Run.state, latest_deadline.c.hard_deadline_at)
            .join(latest_deadline, latest_deadline.c.run_id == Run.run_id)
            .filter(~Run.state.in_(list(TERMINAL_STATES)))
            .filter(latest_deadline.c.hard_deadline_at < evaluated_at)
            .all()
        )
        db_session.rollback()

        expired: List[str] = []
        for run_id_value, state, hard_deadline_at in overdue:
            run_id = str(run_id_value)
            reason = "hard deadline {} passed".format(
                hard_deadline_at.isoformat() if hard_deadline_at is not None else "?")
            try:
                if state in _CANCEL_STATES:
                    advance_to_cancelled(
                        db_session=db_session, run_id=run_id,
                        actor=DEADLINE_ACTOR, reason=reason)
                    target = resolve_cancel_target_client(db_session=db_session, run_id=run_id)
                    if target is not None:
                        acknowledge_client_cancellation(
                            db_session=db_session, run_id=run_id, client_id=target[0])
                    db_session.commit()
                else:
                    event = _DEADLINE_EVENT_BY_STATE.get(state, None)
                    if event is None:
                        continue
                    run_state_transition(
                        db_session=db_session, run_id=run_id, event=event,
                        actor=DEADLINE_ACTOR, reason=reason)
                expired.append(run_id)
            except Exception as xcpt:
                db_session.rollback()
                _LOGGER.warning(
                    "pychestrate.reconcile.deadline_expiry_failed run_id=%s state=%s err=%s",
                    run_id, getattr(state, "value", state), xcpt)
        rtnval = expired
        return rtnval

    def reconcile_on_reconnect(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            client_id: str,
            client_reported_state: RunState,
            note: Optional[str] = None
    ) -> ReconcileDecision:
        """
            Compare the service-side run state with the client's
            reported state and persist a :class:`ReconcileDecision`.

            * If the client reports a terminal state and the
              service is non-terminal, transition to the client's
              truth via the run-state-machine and record a
              ``DIVERGENCE_RESOLVED`` decision.
            * If both sides agree (or the service is already
              terminal in the same outcome), record ``NO_CHANGE``.
            * Anything else falls back to ``NEEDS_INVESTIGATION``.

            :returns: The persisted :class:`ReconcileDecision`.
        """
        snapshot = get_snapshot(db_session=db_session, run_id=run_id)
        prior_state = snapshot.state
        resolved_state = prior_state
        outcome = ReconcileOutcome.NO_CHANGE

        if is_terminal(state=client_reported_state):
            if is_terminal(state=prior_state):
                if prior_state == client_reported_state:
                    outcome = ReconcileOutcome.NO_CHANGE
                else:
                    outcome = ReconcileOutcome.NEEDS_INVESTIGATION
            else:
                run_state_reconcile(
                    db_session=db_session,
                    run_id=run_id,
                    client_reported_state=client_reported_state,
                    source="client_truth",
                    actor="system:reconciler",
                )
                resolved_state = client_reported_state
                outcome = ReconcileOutcome.DIVERGENCE_RESOLVED
        else:
            # Non-terminal client report. M1 only persists the
            # observation; M2 wires progress-resumed transitions
            # explicitly.
            outcome = ReconcileOutcome.PROGRESS_RESUMED

        row = ReconcileDecision(
            decision_id=new_uuid(),
            run_id=run_id,
            project_id=project_id,
            client_id=client_id,
            prior_state=prior_state.value,
            resolved_state=resolved_state.value,
            outcome=outcome,
            source="client_truth",
            note=note,
            decided_at=utc_now(),
        )
        db_session.add(row)
        db_session.flush()
        db_session.commit()
        return row
