"""
.. module:: orchestration.test.flake.repository
    :synopsis: CRUD helpers for flake-tracking rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.orchestration.test.flake.models import (
    FlakeClass,
    FlakeClassification,
    FlakeQuarantineLedger,
    Outcome,
    QuarantineAction,
    TestOutcome,
)


def insert_test_outcome(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        run_id: str,
        runtime_env_digest: str,
        outcome: Outcome,
        duration_ms: int,
        started_at: datetime
    ) -> TestOutcome:
    row = TestOutcome(
        outcome_id=new_uuid(),
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        run_id=run_id,
        runtime_env_digest=runtime_env_digest,
        outcome=outcome,
        duration_ms=duration_ms,
        started_at=started_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_outcome_by_run_and_identity(
        *,
        db_session: DbSession,
        run_id: str,
        test_case_identity_sha256: str
    ) -> Optional[TestOutcome]:
    rtnval = (
        db_session.query(TestOutcome)
        .filter(TestOutcome.run_id == run_id)
        .filter(
            TestOutcome.test_case_identity_sha256 == test_case_identity_sha256,
        )
        .first()
    )
    return rtnval


def list_history_for_test_case(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: Optional[str],
        limit: int
    ) -> List[TestOutcome]:
    query = (
        db_session.query(TestOutcome)
        .filter(TestOutcome.project_id == project_id)
        .filter(TestOutcome.catalog_entry_id == catalog_entry_id)
        .filter(
            TestOutcome.test_case_identity_sha256 == test_case_identity_sha256,
        )
    )
    if runtime_env_digest is not None:
        query = query.filter(
            TestOutcome.runtime_env_digest == runtime_env_digest,
        )
    rows = (
        query.order_by(TestOutcome.started_at.desc()).limit(limit).all()
    )
    rtnval = list(rows)
    return rtnval


def upsert_classification(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: str,
        classification: FlakeClass,
        classifier_name: str,
        classifier_version: str,
        sample_count: int,
        rationale_tag: str,
        last_computed_at: datetime
    ) -> FlakeClassification:
    """
        Insert or update a classification row. Tests-friendly —
        avoids dialect-specific INSERT ... ON CONFLICT UPDATE.
    """
    row = (
        db_session.query(FlakeClassification)
        .filter(FlakeClassification.project_id == project_id)
        .filter(FlakeClassification.catalog_entry_id == catalog_entry_id)
        .filter(
            FlakeClassification.test_case_identity_sha256
            == test_case_identity_sha256,
        )
        .filter(
            FlakeClassification.runtime_env_digest == runtime_env_digest,
        )
        .first()
    )
    if row is None:
        row = FlakeClassification(
            project_id=project_id,
            catalog_entry_id=catalog_entry_id,
            test_case_identity_sha256=test_case_identity_sha256,
            runtime_env_digest=runtime_env_digest,
            classification=classification,
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            sample_count=sample_count,
            rationale_tag=rationale_tag,
            last_computed_at=last_computed_at,
        )
        db_session.add(row)
    else:
        row.classification = classification
        row.classifier_name = classifier_name
        row.classifier_version = classifier_version
        row.sample_count = sample_count
        row.rationale_tag = rationale_tag
        row.last_computed_at = last_computed_at
    db_session.flush()
    return row


def find_classification(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: str
    ) -> Optional[FlakeClassification]:
    rtnval = (
        db_session.query(FlakeClassification)
        .filter(FlakeClassification.project_id == project_id)
        .filter(FlakeClassification.catalog_entry_id == catalog_entry_id)
        .filter(
            FlakeClassification.test_case_identity_sha256
            == test_case_identity_sha256,
        )
        .filter(
            FlakeClassification.runtime_env_digest == runtime_env_digest,
        )
        .first()
    )
    return rtnval


def insert_ledger_entry(
        *,
        db_session: DbSession,
        project_id: str,
        catalog_entry_id: str,
        test_case_identity_sha256: str,
        runtime_env_digest: str,
        action: QuarantineAction,
        actor_id: Optional[str],
        reason: str,
        at_ts: datetime
    ) -> FlakeQuarantineLedger:
    row = FlakeQuarantineLedger(
        ledger_id=new_uuid(),
        project_id=project_id,
        catalog_entry_id=catalog_entry_id,
        test_case_identity_sha256=test_case_identity_sha256,
        runtime_env_digest=runtime_env_digest,
        action=action,
        actor_id=actor_id,
        reason=reason,
        at_ts=at_ts,
    )
    db_session.add(row)
    db_session.flush()
    return row
