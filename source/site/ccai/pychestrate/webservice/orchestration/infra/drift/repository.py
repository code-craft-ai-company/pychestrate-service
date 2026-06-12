"""
.. module:: orchestration.infra.drift.repository
    :synopsis: CRUD helpers for drift rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.infra.drift.models import (
    DriftRun,
    DriftRunState,
    DriftSchedule,
    DriftTickLedger,
    DriftTriggerKind,
)


def upsert_schedule(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        checker_name: str,
        cron_expression: str,
        enabled: bool,
        updated_by: Optional[str],
        updated_at: datetime
    ) -> DriftSchedule:
    row = (
        db_session.query(DriftSchedule)
        .filter(DriftSchedule.project_id == project_id)
        .filter(DriftSchedule.environment_id == environment_id)
        .first()
    )
    if row is None:
        row = DriftSchedule(
            project_id=project_id,
            environment_id=environment_id,
            checker_name=checker_name,
            cron_expression=cron_expression,
            enabled=enabled,
            updated_by=updated_by,
            updated_at=updated_at,
        )
        db_session.add(row)
    else:
        row.checker_name = checker_name
        row.cron_expression = cron_expression
        row.enabled = enabled
        row.updated_by = updated_by
        row.updated_at = updated_at
    db_session.flush()
    return row


def find_schedule(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str
    ) -> Optional[DriftSchedule]:
    rtnval = (
        db_session.query(DriftSchedule)
        .filter(DriftSchedule.project_id == project_id)
        .filter(DriftSchedule.environment_id == environment_id)
        .first()
    )
    return rtnval


def insert_drift_run(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        checker_name: str,
        trigger_kind: DriftTriggerKind,
        scheduled_for: datetime
    ) -> DriftRun:
    row = DriftRun(
        run_id=new_uuid(),
        project_id=project_id,
        environment_id=environment_id,
        checker_name=checker_name,
        state=DriftRunState.PENDING,
        trigger_kind=trigger_kind,
        scheduled_for=scheduled_for,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_run_by_id(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[DriftRun]:
    rtnval = (
        db_session.query(DriftRun)
        .filter(DriftRun.run_id == run_id)
        .first()
    )
    return rtnval


def list_runs_for_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        limit: int
    ) -> List[DriftRun]:
    rows = (
        db_session.query(DriftRun)
        .filter(DriftRun.environment_id == environment_id)
        .order_by(DriftRun.scheduled_for.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_tick_ledger(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        scheduled_for: datetime
    ) -> Optional[DriftTickLedger]:
    rtnval = (
        db_session.query(DriftTickLedger)
        .filter(DriftTickLedger.project_id == project_id)
        .filter(DriftTickLedger.environment_id == environment_id)
        .filter(DriftTickLedger.scheduled_for == scheduled_for)
        .first()
    )
    return rtnval


def insert_tick_ledger(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        scheduled_for: datetime,
        run_id: str,
        recorded_at: datetime
    ) -> DriftTickLedger:
    row = DriftTickLedger(
        project_id=project_id,
        environment_id=environment_id,
        scheduled_for=scheduled_for,
        run_id=run_id,
        recorded_at=recorded_at,
    )
    db_session.add(row)
    db_session.flush()
    return row
