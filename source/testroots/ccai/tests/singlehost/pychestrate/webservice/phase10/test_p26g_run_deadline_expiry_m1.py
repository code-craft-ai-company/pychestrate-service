"""
.. module:: test_p26g_run_deadline_expiry_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The reconciler ends runs past their hard deadline (E2E-16).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta
from typing import Any, List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid, utc_now
from ccai.pychestrate.webservice.jobs.envelope.models import JobEnvelopeRecord
from ccai.pychestrate.webservice.jobs.reconcile.reconciler import RunReconciler
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    RunState,
    create_run,
    transition,
)
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus

# Side-effect imports so the dispatch, cancel and envelope tables exist.
from ccai.pychestrate.webservice.jobs.cancel import models as _cancel_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000777"


def _run_with_deadline(*, session: Any, events: List[RunEvent], hard_deadline_at: datetime) -> str:
    """
        Create a run, drive it through ``events``, and archive an envelope
        carrying ``hard_deadline_at`` for it.
    """
    reset_event_bus()
    run_id = new_uuid()
    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="testbase")
    for event in events:
        transition(db_session=session, run_id=run_id, event=event, actor="test")
    session.add(JobEnvelopeRecord(
        envelope_id=new_uuid(), schema_version="2026-04-24", project_id=PROJECT_UUID,
        run_id=run_id, job_id=new_uuid(), job_type="testbase", client_id=new_uuid(),
        pod_id=new_uuid(), issued_at=hard_deadline_at - timedelta(minutes=15),
        hard_deadline_at=hard_deadline_at, key_id="k", canonical_payload=b"{}",
        signature=b"s", canonical_payload_text="{}",
    ))
    session.commit()
    rtnval = run_id
    return rtnval


_RUNNING = [RunEvent.DISPATCH_STARTED, RunEvent.RECEIPT_RECORDED, RunEvent.FIRST_PROGRESS]


def test_running_run_past_its_hard_deadline_fails():
    """
    **Feature: deadline enforcement (E2E-16)**
    **Property: a running run whose hard deadline has passed is ended as
    FAILED by the reconciler.**
    """
    _engine, session = build_in_memory_session()
    run_id = _run_with_deadline(session=session, events=_RUNNING,
                                hard_deadline_at=utc_now() - timedelta(minutes=1))

    expired = RunReconciler().expire_overdue_runs(db_session=session)

    testbase.assert_equal(expired, [run_id])
    testbase.assert_equal(run_repo.find_run(db_session=session, run_id=run_id).state, RunState.FAILED)
    return


def test_run_awaiting_a_cancel_past_its_deadline_ends_cancelled():
    """
    **Feature: deadline enforcement (E2E-16)**
    **Property: a run stuck in CANCEL_REQUESTED past its hard deadline --
    its pod never confirmed the cancel -- ends CANCELLED, not FAILED.**
    """
    _engine, session = build_in_memory_session()
    run_id = _run_with_deadline(session=session, events=_RUNNING + [RunEvent.CANCEL_REQUESTED],
                                hard_deadline_at=utc_now() - timedelta(minutes=1))

    RunReconciler().expire_overdue_runs(db_session=session)

    testbase.assert_equal(run_repo.find_run(db_session=session, run_id=run_id).state, RunState.CANCELLED)
    return


def test_never_acknowledged_dispatch_past_its_deadline_fails_to_dispatch():
    """
    **Feature: deadline enforcement (E2E-16)**
    **Property: a run still DISPATCHING at its hard deadline ends
    DISPATCH_FAILED -- the pod never took it.**
    """
    _engine, session = build_in_memory_session()
    run_id = _run_with_deadline(session=session, events=[RunEvent.DISPATCH_STARTED],
                                hard_deadline_at=utc_now() - timedelta(minutes=1))

    RunReconciler().expire_overdue_runs(db_session=session)

    testbase.assert_equal(run_repo.find_run(db_session=session, run_id=run_id).state,
                          RunState.DISPATCH_FAILED)
    return


def test_run_before_its_deadline_is_left_alone():
    """
    **Feature: deadline enforcement (E2E-16)**
    **Property: a run whose hard deadline is still ahead is not touched.**
    """
    _engine, session = build_in_memory_session()
    run_id = _run_with_deadline(session=session, events=_RUNNING,
                                hard_deadline_at=utc_now() + timedelta(minutes=10))

    expired = RunReconciler().expire_overdue_runs(db_session=session)

    testbase.assert_equal(expired, [])
    testbase.assert_equal(run_repo.find_run(db_session=session, run_id=run_id).state, RunState.RUNNING)
    return
