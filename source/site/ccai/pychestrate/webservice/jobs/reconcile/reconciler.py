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


from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.reconcile.models import (
    ReconcileDecision,
    ReconcileOutcome,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    Run,
    RunState,
    TERMINAL_STATES,
    get_snapshot,
    is_terminal,
    reconcile as run_state_reconcile,
)


class RunReconciler:
    """
        Decision engine for client-reconnect reconciliation.
    """

    def scan_once(
            self,
            *,
            db_session: DbSession
        ) -> int:
        """
            Periodic-tick entry point. Counts the runs currently in
            a non-terminal state — the population the reconciler is
            responsible for tracking. PR A wires the scheduler to
            invoke this method on a cadence so the loop is alive
            even though the policy-driven scan (compare client
            truth, emit divergence events) lands in a subsequent
            PR. Idempotent and side-effect-free.

            :param db_session: Active SQLAlchemy session.

            :returns: Count of non-terminal runs observed.
        """
        terminal_members = list(TERMINAL_STATES)
        rows = (
            db_session.query(Run)
            .filter(~Run.state.in_(terminal_members))
            .all()
        )
        rtnval = len(rows)
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
