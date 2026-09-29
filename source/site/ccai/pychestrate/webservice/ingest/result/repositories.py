"""
.. module:: ingest.result.repositories
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for result-tree persistence.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Dict, List, Optional

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.ingest.result.factories.parser_protocol import (
    ParsedArtifact,
    ParsedSummary,
    ParsedTaskResult,
)
from ccai.pychestrate.webservice.ingest.result.models import (
    ResultScanAttempt,
    RunArtifact,
    RunResultSummary,
    ScanOutcomeStatus,
    TaskResult,
)


def upsert_summary(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        parser_tag: str,
        summary: ParsedSummary,
        ingested_at: datetime
    ) -> RunResultSummary:
    """
        Insert or update the run-level result summary.
    """
    row = (
        db_session.query(RunResultSummary)
        .filter(RunResultSummary.run_id == run_id)
        .first()
    )
    if row is None:
        row = RunResultSummary(
            summary_id=new_uuid(),
            run_id=run_id,
            project_id=project_id,
            parser_tag=parser_tag,
            tests_total=summary.tests_total,
            tests_passed=summary.tests_passed,
            tests_failed=summary.tests_failed,
            tests_skipped=summary.tests_skipped,
            tests_errored=summary.tests_errored,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            ingested_at=ingested_at,
            raw_payload=dict(summary.raw),
        )
        db_session.add(row)
    else:
        row.parser_tag = parser_tag
        row.tests_total = summary.tests_total
        row.tests_passed = summary.tests_passed
        row.tests_failed = summary.tests_failed
        row.tests_skipped = summary.tests_skipped
        row.tests_errored = summary.tests_errored
        row.started_at = summary.started_at
        row.finished_at = summary.finished_at
        row.ingested_at = ingested_at
        row.raw_payload = dict(summary.raw)
    db_session.flush()
    return row


def upsert_task_result(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        task: ParsedTaskResult,
        ingested_at: datetime
    ) -> TaskResult:
    """
        Insert or update one task result row, idempotent on
        ``(run_id, instance_uuid)``.
    """
    row = (
        db_session.query(TaskResult)
        .filter(TaskResult.run_id == run_id)
        .filter(TaskResult.instance_uuid == task.instance_uuid)
        .first()
    )
    if row is None:
        row = TaskResult(
            task_id=new_uuid(),
            run_id=run_id,
            project_id=project_id,
            test_name=task.test_name,
            instance_uuid=task.instance_uuid,
            rtype=task.rtype,
            result=task.result,
            started_at=task.started_at,
            finished_at=task.finished_at,
            ingested_at=ingested_at,
            raw_payload=dict(task.raw),
        )
        db_session.add(row)
    else:
        row.test_name = task.test_name
        row.rtype = task.rtype
        row.result = task.result
        row.started_at = task.started_at
        row.finished_at = task.finished_at
        row.ingested_at = ingested_at
        row.raw_payload = dict(task.raw)
    db_session.flush()
    return row


def upsert_artifact(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        artifact: ParsedArtifact,
        ingested_at: datetime
    ) -> RunArtifact:
    """
        Insert or update one artifact row, idempotent on
        ``(run_id, relative_path)``.
    """
    row = (
        db_session.query(RunArtifact)
        .filter(RunArtifact.run_id == run_id)
        .filter(RunArtifact.relative_path == artifact.relative_path)
        .first()
    )
    if row is None:
        row = RunArtifact(
            artifact_id=new_uuid(),
            run_id=run_id,
            project_id=project_id,
            relative_path=artifact.relative_path,
            classification=artifact.classification,
            size_bytes=artifact.size_bytes,
            content_type=artifact.content_type,
            ingested_at=ingested_at,
        )
        db_session.add(row)
    else:
        row.classification = artifact.classification
        row.size_bytes = artifact.size_bytes
        row.content_type = artifact.content_type
        row.ingested_at = ingested_at
    db_session.flush()
    return row


def insert_scan_attempt(
        *,
        db_session: DbSession,
        run_id: str,
        started_at: datetime
    ) -> ResultScanAttempt:
    """
        Open a fresh scan attempt row in ``SCANNED`` (the
        optimistic state — :func:`finalize_scan_attempt` flips it
        to NOT_FOUND or FAILED on the unhappy paths).
    """
    row = ResultScanAttempt(
        attempt_id=new_uuid(),
        run_id=run_id,
        started_at=started_at,
        status=ScanOutcomeStatus.SCANNED,
        files_seen=0,
        artifacts_persisted=0,
        tasks_persisted=0,
    )
    db_session.add(row)
    db_session.flush()
    return row


def finalize_scan_attempt(
        *,
        db_session: DbSession,
        attempt: ResultScanAttempt,
        finished_at: datetime,
        status: ScanOutcomeStatus,
        files_seen: int,
        artifacts_persisted: int,
        tasks_persisted: int,
        failure_reason: Optional[str]
    ) -> None:
    """
        Mark the scan attempt complete with its observed counts.
    """
    attempt.finished_at = finished_at
    attempt.status = status
    attempt.files_seen = files_seen
    attempt.artifacts_persisted = artifacts_persisted
    attempt.tasks_persisted = tasks_persisted
    attempt.failure_reason = failure_reason
    db_session.flush()
    return


def find_summary(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[RunResultSummary]:
    """
        Return the persisted summary row or ``None``.
    """
    rtnval = (
        db_session.query(RunResultSummary)
        .filter(RunResultSummary.run_id == run_id)
        .first()
    )
    return rtnval


def list_summaries_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int
    ) -> List[RunResultSummary]:
    """
        Return run-result summary rows for a project, newest
        ``ingested_at`` first, capped at ``limit``.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID.
        :param limit: Hard cap on returned rows.

        :returns: List of :class:`RunResultSummary` rows.
    """
    rows = (
        db_session.query(RunResultSummary)
        .filter(RunResultSummary.project_id == project_id)
        .order_by(RunResultSummary.ingested_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_tasks(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[TaskResult]:
    """
        Return every task row for a run.
    """
    rows = (
        db_session.query(TaskResult)
        .filter(TaskResult.run_id == run_id)
        .order_by(TaskResult.test_name.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


#: Results that are not a problem: a passed test, and one that did not run.
QUIET_RESULTS = ("PASSED", "SKIPPED", "UNSET")


def count_tasks_by_result(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Dict[str, int]:
    """
        Count a run's task rows per result string, without loading the
        payloads.

        :param db_session: Active session.
        :param run_id: Run UUID.

        :returns: ``{"PASSED": 31, "FAILED": 1}``.
    """
    rows = (
        db_session.query(TaskResult.result, sa.func.count(TaskResult.task_id))
        .filter(TaskResult.run_id == run_id)
        .group_by(TaskResult.result)
        .all()
    )
    rtnval = {str(result): int(count) for result, count in rows}
    return rtnval


def page_tasks(
        *,
        db_session: DbSession,
        run_id: str,
        problems_only: bool,
        offset: int,
        limit: int
    ) -> List[TaskResult]:
    """
        One page of a run's task rows, problems first: anything that is not
        passed, skipped or unset (failures, errors, unfamiliar results), then
        skipped and unset, then passed; by test name within each group.

        :param db_session: Active session.
        :param run_id: Run UUID.
        :param problems_only: Leave out the quiet results.
        :param offset: Rows to skip.
        :param limit: Rows to return.

        :returns: The page's rows.
    """
    rank = sa.case(
        (TaskResult.result == "PASSED", 2),
        (TaskResult.result.in_(("SKIPPED", "UNSET")), 1),
        else_=0,
    )
    query = db_session.query(TaskResult).filter(TaskResult.run_id == run_id)
    if problems_only is True:
        query = query.filter(TaskResult.result.notin_(QUIET_RESULTS))
    rows = (
        query.order_by(rank.asc(), TaskResult.test_name.asc(), TaskResult.task_id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_artifacts(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[RunArtifact]:
    """
        Return every artifact row for a run.
    """
    rows = (
        db_session.query(RunArtifact)
        .filter(RunArtifact.run_id == run_id)
        .order_by(RunArtifact.relative_path.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
