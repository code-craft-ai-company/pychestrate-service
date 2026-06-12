"""
.. module:: orchestration.test.triage.repository
    :synopsis: CRUD helpers for triage rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.test.triage.models import (
    TriageCase,
    TriageCaseLedger,
    TriageClass,
)


def insert_case(
        *,
        db_session: DbSession,
        project_id: str,
        run_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        stack_signature_sha256: str,
        classification: TriageClass,
        confidence: float,
        rationale: str,
        classifier_name: str,
        created_at: datetime
    ) -> TriageCase:
    row = TriageCase(
        case_id=new_uuid(),
        project_id=project_id,
        run_id=run_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        stack_signature_sha256=stack_signature_sha256,
        classification=classification,
        confidence=confidence,
        rationale=rationale,
        classifier_name=classifier_name,
        tracker=None,
        ticket_key=None,
        ticket_url=None,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_case_by_id(
        *,
        db_session: DbSession,
        case_id: str
    ) -> Optional[TriageCase]:
    rtnval = (
        db_session.query(TriageCase)
        .filter(TriageCase.case_id == case_id)
        .first()
    )
    return rtnval


def find_case_for_run_test(
        *,
        db_session: DbSession,
        run_id: str,
        test_case_identity_sha256: str
    ) -> Optional[TriageCase]:
    rtnval = (
        db_session.query(TriageCase)
        .filter(TriageCase.run_id == run_id)
        .filter(
            TriageCase.test_case_identity_sha256 == test_case_identity_sha256,
        )
        .first()
    )
    return rtnval


def list_cases_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[TriageCase]:
    rows = (
        db_session.query(TriageCase)
        .filter(TriageCase.run_id == run_id)
        .order_by(TriageCase.created_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_ledger_entry(
        *,
        db_session: DbSession,
        case_id: str,
        actor_id: Optional[str],
        from_class: Optional[TriageClass],
        to_class: TriageClass,
        rationale: str,
        at_ts: datetime
    ) -> TriageCaseLedger:
    row = TriageCaseLedger(
        ledger_id=new_uuid(),
        case_id=case_id,
        actor_id=actor_id,
        from_class=from_class,
        to_class=to_class,
        rationale=rationale,
        at_ts=at_ts,
    )
    db_session.add(row)
    db_session.flush()
    return row
