"""
.. module:: ingest.progress.repositories
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for progress summary / record / counter rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.ingest.progress.models import (
    RunProgressCounters,
    RunProgressFrame,
    RunProgressRecord,
    RunProgressSummary,
)
from ccai.pychestrate.webservice.ingest.progress.schema import (
    ProgressFrameEnvelope,
    ProgressRecord,
    ProgressSummary,
)


def insert_summary(
        *,
        db_session: DbSession,
        summary: ProgressSummary,
        received_at: datetime
    ) -> RunProgressSummary:
    """
        Persist one ``RunProgressSummary`` row.
    """
    row = RunProgressSummary(
        summary_id=new_uuid(),
        run_id=summary.run_id,
        client_id=summary.client_id,
        format_tag=summary.format_tag,
        tests_total=summary.tests_total,
        tests_passed=summary.tests_passed,
        tests_failed=summary.tests_failed,
        tests_skipped=summary.tests_skipped,
        tests_errored=summary.tests_errored,
        percent_complete=summary.percent_complete,
        notes=summary.notes,
        recorded_at=summary.recorded_at,
        received_at=received_at,
        raw_payload=dict(summary.raw),
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_record(
        *,
        db_session: DbSession,
        run_id: str,
        record_index: int
    ) -> Optional[RunProgressRecord]:
    """
        Look up a record by ``(run_id, record_index)``.
    """
    rtnval = (
        db_session.query(RunProgressRecord)
        .filter(RunProgressRecord.run_id == run_id)
        .filter(RunProgressRecord.record_index == record_index)
        .first()
    )
    return rtnval


def insert_record(
        *,
        db_session: DbSession,
        record: ProgressRecord,
        received_at: datetime
    ) -> RunProgressRecord:
    """
        Persist one ``RunProgressRecord`` row.
    """
    row = RunProgressRecord(
        record_id=new_uuid(),
        run_id=record.run_id,
        client_id=record.client_id,
        record_index=record.record_index,
        test_name=record.test_name,
        result=record.result,
        started_at=record.started_at,
        finished_at=record.finished_at,
        duration_seconds=record.duration_seconds,
        received_at=received_at,
        raw_payload=dict(record.raw),
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_records(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[RunProgressRecord]:
    """
        Return every record for ``run_id`` ordered by index.
    """
    rows = (
        db_session.query(RunProgressRecord)
        .filter(RunProgressRecord.run_id == run_id)
        .order_by(RunProgressRecord.record_index.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_frame(
        *,
        db_session: DbSession,
        run_id: str,
        frame_kind: str,
        frame_index: int
    ) -> Optional[RunProgressFrame]:
    """
        Look up a generalized progress frame by
        ``(run_id, frame_kind, frame_index)``.
    """
    rtnval = (
        db_session.query(RunProgressFrame)
        .filter(RunProgressFrame.run_id == run_id)
        .filter(RunProgressFrame.frame_kind == frame_kind)
        .filter(RunProgressFrame.frame_index == frame_index)
        .first()
    )
    return rtnval


def insert_frame(
        *,
        db_session: DbSession,
        frame: ProgressFrameEnvelope,
        received_at: datetime
    ) -> RunProgressFrame:
    """
        Persist one ``RunProgressFrame`` row.
    """
    row = RunProgressFrame(
        frame_id=new_uuid(),
        run_id=frame.run_id,
        client_id=frame.client_id,
        frame_kind=frame.frame_kind,
        frame_index=frame.frame_index,
        phase=frame.phase,
        status=frame.status,
        percent_complete=frame.percent_complete,
        notes=frame.notes,
        recorded_at=frame.recorded_at,
        received_at=received_at,
        raw_payload=dict(frame.payload),
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_frames(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[RunProgressFrame]:
    """
        Return every generalized progress frame for ``run_id``
        ordered by ``(received_at, frame_index)``.
    """
    rows = (
        db_session.query(RunProgressFrame)
        .filter(RunProgressFrame.run_id == run_id)
        .order_by(
            RunProgressFrame.received_at.asc(),
            RunProgressFrame.frame_index.asc(),
        )
        .all()
    )
    rtnval = list(rows)
    return rtnval


def latest_frame(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[RunProgressFrame]:
    """
        Return the most recently received generalized progress
        frame for ``run_id``, or ``None`` when none has landed.
    """
    rtnval = (
        db_session.query(RunProgressFrame)
        .filter(RunProgressFrame.run_id == run_id)
        .order_by(
            RunProgressFrame.received_at.desc(),
            RunProgressFrame.frame_index.desc(),
        )
        .first()
    )
    return rtnval


def get_counters(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[RunProgressCounters]:
    """
        Fetch the rolling counter row, or ``None`` if not yet
        materialized.
    """
    rtnval = (
        db_session.query(RunProgressCounters)
        .filter(RunProgressCounters.run_id == run_id)
        .first()
    )
    return rtnval


def upsert_counters_from_summary(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        summary: ProgressSummary,
        last_summary_at: datetime
    ) -> RunProgressCounters:
    """
        Insert or update the rolling counter row from a summary.
    """
    existing = get_counters(db_session=db_session, run_id=run_id)
    if existing is None:
        existing = RunProgressCounters(
            run_id=run_id,
            project_id=project_id,
            tests_total=summary.tests_total,
            tests_passed=summary.tests_passed,
            tests_failed=summary.tests_failed,
            tests_skipped=summary.tests_skipped,
            tests_errored=summary.tests_errored,
            percent_complete=summary.percent_complete,
            last_summary_at=last_summary_at,
        )
        db_session.add(existing)
    else:
        existing.tests_total = summary.tests_total
        existing.tests_passed = summary.tests_passed
        existing.tests_failed = summary.tests_failed
        existing.tests_skipped = summary.tests_skipped
        existing.tests_errored = summary.tests_errored
        existing.percent_complete = summary.percent_complete
        existing.last_summary_at = last_summary_at
    db_session.flush()
    return existing


def latest_summary(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[RunProgressSummary]:
    """
        Return the most recently received summary for ``run_id``.
    """
    rtnval = (
        db_session.query(RunProgressSummary)
        .filter(RunProgressSummary.run_id == run_id)
        .order_by(RunProgressSummary.received_at.desc())
        .first()
    )
    return rtnval
