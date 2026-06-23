"""
.. module:: orchestration.test.compare.repository
    :synopsis: CRUD helpers for compare-report rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.test.compare.models import (
    CompareReport,
    CompareStatus,
)


def insert_report(
        *,
        db_session: DbSession,
        project_id: str,
        base_run_id: str,
        candidate_run_id: str,
        per_test_count: int,
        per_test_payload: List[Dict[str, Any]],
        warnings: List[str],
        note: str,
        computed_at: datetime,
        expires_at: datetime
    ) -> CompareReport:
    row = CompareReport(
        report_id=new_uuid(),
        project_id=project_id,
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        status=CompareStatus.READY,
        per_test_count=per_test_count,
        per_test_payload=list(per_test_payload),
        warnings=list(warnings),
        note=note,
        computed_at=computed_at,
        expires_at=expires_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_report_by_id(
        *,
        db_session: DbSession,
        report_id: str
    ) -> Optional[CompareReport]:
    rtnval = (
        db_session.query(CompareReport)
        .filter(CompareReport.report_id == report_id)
        .first()
    )
    return rtnval


def find_report_by_run_pair(
        *,
        db_session: DbSession,
        base_run_id: str,
        candidate_run_id: str
    ) -> Optional[CompareReport]:
    rtnval = (
        db_session.query(CompareReport)
        .filter(CompareReport.base_run_id == base_run_id)
        .filter(CompareReport.candidate_run_id == candidate_run_id)
        .first()
    )
    return rtnval
