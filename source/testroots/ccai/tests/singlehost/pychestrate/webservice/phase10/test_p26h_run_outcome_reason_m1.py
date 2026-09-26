"""
.. module:: test_p26h_run_outcome_reason_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The run detail explains how the run ended (E2E-15).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.jobs.run.state import RunEvent, create_run, transition
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.messaging.event_bus import reset_event_bus
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000888"


def _failed_run(*, session, reason):
    reset_event_bus()
    run_id = new_uuid()
    create_run(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="testbase")
    for event in (RunEvent.DISPATCH_STARTED, RunEvent.RECEIPT_RECORDED):
        transition(db_session=session, run_id=run_id, event=event, actor="test")
    transition(db_session=session, run_id=run_id, event=RunEvent.FAILURE_OBSERVED,
               actor="test", reason=reason)
    rtnval = run_repo.find_run(db_session=session, run_id=run_id)
    return rtnval


def test_outcome_reason_prefers_the_pods_manifest_notes():
    """
    **Feature: run outcome reason (E2E-15)**
    **Property: the pod's notes on its result manifest explain the run.**
    """
    _engine, session = build_in_memory_session()
    row = _failed_run(session=session, reason="result ingest")

    reason = runs_routes._outcome_reason(
        db_session=session, row=row,
        result_manifest={"notes": "Build source acquisition failed: no git_url"})

    testbase.assert_equal(reason, "Build source acquisition failed: no git_url")
    return


def test_outcome_reason_falls_back_to_the_terminal_transition():
    """
    **Feature: run outcome reason (E2E-15)**
    **Property: without manifest notes, the reason recorded with the
    transition into the terminal state explains the run.**
    """
    _engine, session = build_in_memory_session()
    row = _failed_run(session=session, reason="REJECTED: envelope verification failed")

    reason = runs_routes._outcome_reason(db_session=session, row=row, result_manifest=None)

    testbase.assert_equal(reason, "REJECTED: envelope verification failed")
    return
