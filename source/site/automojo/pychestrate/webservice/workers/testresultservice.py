"""
.. module:: workers.testresultservice
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-layer operations for first-class test results.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.jobmodels import WorkerJob
from automojo.pychestrate.webservice.workers.testresultmodels import (
    TestOutcome,
    WorkerJobTestResult,
)


@dataclass(frozen=True)
class TestResultView:
    """
        Caller-facing snapshot of a :class:`WorkerJobTestResult`.
    """
    result_id: str
    job_id: str
    worker_id: Optional[str]
    attempt: int
    suite_name: str
    case_name: str
    outcome: str
    duration_seconds: float
    started_at: Optional[str]
    completed_at: str
    failure_message: Optional[str]
    failure_trace: Optional[str]
    attributes: Dict[str, Any]


def _to_view(*, row: WorkerJobTestResult) -> TestResultView:
    if row.worker_id is not None:
        worker_field: Optional[str] = str(row.worker_id)
    else:
        worker_field = None
    if row.started_at is not None:
        started_field: Optional[str] = row.started_at.isoformat()
    else:
        started_field = None
    if row.attributes is not None:
        attrs = dict(row.attributes)
    else:
        attrs = {}
    rtnval = TestResultView(
        result_id=str(row.result_id),
        job_id=str(row.job_id),
        worker_id=worker_field,
        attempt=int(row.attempt) if row.attempt is not None else 1,
        suite_name=row.suite_name if row.suite_name is not None else "",
        case_name=row.case_name,
        outcome=row.outcome,
        duration_seconds=(
            float(row.duration_seconds)
            if row.duration_seconds is not None else 0.0
        ),
        started_at=started_field,
        completed_at=row.completed_at.isoformat(),
        failure_message=row.failure_message,
        failure_trace=row.failure_trace,
        attributes=attrs,
    )
    return rtnval


def _coerce_outcome(*, value: Any) -> str:
    if value is None:
        err_lines = [
            "Test result outcome is required.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if isinstance(value, TestOutcome):
        rtnval = value.value
        return rtnval
    raw = str(value).strip()
    if len(raw) == 0:
        err_lines = [
            "Test result outcome cannot be empty.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    rtnval = raw
    return rtnval


def _parse_iso_datetime(*, value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    rtnval = parsed
    return rtnval


def record_test_result(
        *,
        db_session: DbSession,
        job_id: str,
        worker_id: Optional[str],
        case_name: str,
        outcome: Any,
        suite_name: str = "",
        duration_seconds: float = 0.0,
        started_at: Any = None,
        completed_at: Any = None,
        failure_message: Optional[str] = None,
        failure_trace: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TestResultView:
    """
        Insert one test result attached to ``job_id``.

        :raises LookupError: When ``job_id`` is unknown.
        :raises ValueError: When ``case_name`` or ``outcome`` is
                            empty / missing.
    """
    if case_name is None or len(str(case_name).strip()) == 0:
        err_lines = [
            "Test result case_name is required.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    outcome_value = _coerce_outcome(value=outcome)

    job_row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if job_row is None:
        err_lines = [
            "Worker job not found.",
            "JOB_ID: {}".format(job_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise LookupError(err_msg) from None

    attempt_value = (
        int(job_row.attempt) if job_row.attempt is not None else 1
    )
    started_dt = _parse_iso_datetime(value=started_at)
    completed_dt = _parse_iso_datetime(value=completed_at)
    if completed_dt is None:
        completed_dt = datetime.now(timezone.utc)
    if attributes is None:
        attrs_value: Dict[str, Any] = {}
    else:
        attrs_value = dict(attributes)
    if duration_seconds is None:
        duration_value = 0.0
    else:
        try:
            duration_value = float(duration_seconds)
        except (TypeError, ValueError):
            duration_value = 0.0

    row = WorkerJobTestResult(
        result_id=new_uuid(),
        job_id=job_id,
        worker_id=worker_id,
        attempt=attempt_value,
        suite_name=str(suite_name) if suite_name is not None else "",
        case_name=str(case_name).strip(),
        outcome=outcome_value,
        duration_seconds=duration_value,
        started_at=started_dt,
        completed_at=completed_dt,
        failure_message=failure_message,
        failure_trace=failure_trace,
        attributes=attrs_value,
    )
    db_session.add(row)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def record_test_results_batch(
        *,
        db_session: DbSession,
        job_id: str,
        worker_id: Optional[str],
        results: List[Dict[str, Any]],
    ) -> List[TestResultView]:
    """
        Bulk-insert test results for ``job_id``. Validates every
        entry first so a single bad row doesn't leave a
        half-written batch on the floor; commits once at the
        end.

        :raises LookupError: When ``job_id`` is unknown.
        :raises ValueError: On any validation failure (with the
                            offending index in the message).
    """
    if results is None:
        rtnval: List[TestResultView] = []
        return rtnval
    if len(results) == 0:
        return []

    job_row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if job_row is None:
        err_lines = [
            "Worker job not found.",
            "JOB_ID: {}".format(job_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise LookupError(err_msg) from None
    attempt_value = (
        int(job_row.attempt) if job_row.attempt is not None else 1
    )

    # Validate up front so we don't half-commit.
    prepared: List[WorkerJobTestResult] = []
    for index, entry in enumerate(results):
        if not isinstance(entry, dict):
            err_lines = [
                "Test result entry must be an object.",
                "INDEX: {}".format(index),
                "FOUND_TYPE: {}".format(type(entry).__name__),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        case_name = entry.get("case_name", None)
        if case_name is None or len(str(case_name).strip()) == 0:
            err_lines = [
                "Test result case_name is required.",
                "INDEX: {}".format(index),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        outcome_value = _coerce_outcome(value=entry.get("outcome", None))

        started_dt = _parse_iso_datetime(value=entry.get("started_at", None))
        completed_dt = _parse_iso_datetime(value=entry.get("completed_at", None))
        if completed_dt is None:
            completed_dt = datetime.now(timezone.utc)
        attrs_raw = entry.get("attributes", {})
        if attrs_raw is None:
            attrs_value: Dict[str, Any] = {}
        elif isinstance(attrs_raw, dict):
            attrs_value = dict(attrs_raw)
        else:
            err_lines = [
                "Test result attributes must be an object.",
                "INDEX: {}".format(index),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        duration_raw = entry.get("duration_seconds", 0.0)
        try:
            duration_value = float(duration_raw)
        except (TypeError, ValueError):
            duration_value = 0.0
        suite_value = entry.get("suite_name", "")
        if suite_value is None:
            suite_value = ""

        prepared.append(WorkerJobTestResult(
            result_id=new_uuid(),
            job_id=job_id,
            worker_id=worker_id,
            attempt=attempt_value,
            suite_name=str(suite_value),
            case_name=str(case_name).strip(),
            outcome=outcome_value,
            duration_seconds=duration_value,
            started_at=started_dt,
            completed_at=completed_dt,
            failure_message=entry.get("failure_message", None),
            failure_trace=entry.get("failure_trace", None),
            attributes=attrs_value,
        ))

    for r in prepared:
        db_session.add(r)
    db_session.commit()
    rtnval = [_to_view(row=r) for r in prepared]
    return rtnval


def list_test_results_for_job(
        *,
        db_session: DbSession,
        job_id: str,
        outcome: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> List[TestResultView]:
    """
        Return every result attached to ``job_id``, oldest
        first. Optional ``outcome`` and ``attempt`` filters.
    """
    query = (
        db_session.query(WorkerJobTestResult)
        .filter(WorkerJobTestResult.job_id == job_id)
    )
    if outcome is not None and len(str(outcome)) > 0:
        query = query.filter(
            WorkerJobTestResult.outcome == str(outcome),
        )
    if attempt is not None:
        query = query.filter(
            WorkerJobTestResult.attempt == int(attempt),
        )
    rows = (
        query.order_by(WorkerJobTestResult.completed_at.asc())
        .all()
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def summarize_test_results_for_job(
        *,
        db_session: DbSession,
        job_id: str,
    ) -> Dict[str, Any]:
    """
        Return ``{by_outcome: {passed, failed, ...}, total,
        passed, failed, skipped, errored}`` for the job's
        results across every attempt. The conventional
        outcomes are always present (with ``0`` when empty);
        non-conventional outcomes appear under their literal
        name.
    """
    rows = (
        db_session.query(
            WorkerJobTestResult.outcome,
            sa_func.count().label("count"),
        )
        .filter(WorkerJobTestResult.job_id == job_id)
        .group_by(WorkerJobTestResult.outcome)
        .all()
    )
    by_outcome: Dict[str, int] = {}
    for member in TestOutcome:
        by_outcome[member.value] = 0
    for outcome_value, count_value in rows:
        by_outcome[outcome_value] = int(count_value)
    total = sum(by_outcome.values())
    rtnval = {
        "by_outcome": by_outcome,
        "total": total,
        "passed": by_outcome.get(TestOutcome.PASSED.value, 0),
        "failed": by_outcome.get(TestOutcome.FAILED.value, 0),
        "skipped": by_outcome.get(TestOutcome.SKIPPED.value, 0),
        "errored": by_outcome.get(TestOutcome.ERRORED.value, 0),
    }
    return rtnval
