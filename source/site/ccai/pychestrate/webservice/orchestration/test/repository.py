"""
.. module:: orchestration.test.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestRunRepository — CRUD helpers.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.orchestration.test.models import (
    TestRun,
    TestRunState,
)


def insert_run(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        catalog_entry_id: str,
        runner_kind: str,
        triggered_by: Optional[str],
        triggered_at: datetime,
        inputs_json: dict
    ) -> TestRun:
    """
        Insert a fresh ``TestRun`` row in
        :attr:`TestRunState.TRIGGERED`.
    """
    row = TestRun(
        run_id=run_id,
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        runner_kind=runner_kind,
        triggered_by=triggered_by,
        state=TestRunState.TRIGGERED,
        triggered_at=triggered_at,
        inputs_json=dict(inputs_json),
    )
    db_session.add(row)
    db_session.flush()
    return row


def get_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[TestRun]:
    """
        Fetch a TestRun row.
    """
    rtnval = (
        db_session.query(TestRun)
        .filter(TestRun.run_id == run_id)
        .first()
    )
    return rtnval


def update_state(
        *,
        db_session: DbSession,
        run: TestRun,
        new_state: TestRunState,
        failure_reason: Optional[str] = None,
        dispatch_attempt_id: Optional[str] = None,
        finished_at: Optional[datetime] = None
    ) -> None:
    """
        Apply a state change to a TestRun row.
    """
    run.state = new_state
    if failure_reason is not None:
        run.failure_reason = failure_reason
    if dispatch_attempt_id is not None:
        run.dispatch_attempt_id = dispatch_attempt_id
    if finished_at is not None:
        run.finished_at = finished_at
    db_session.flush()
    return


def list_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[TestRun]:
    """
        Return every test run for a project.
    """
    rows = (
        db_session.query(TestRun)
        .filter(TestRun.project_id == project_id)
        .order_by(TestRun.triggered_at.desc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
