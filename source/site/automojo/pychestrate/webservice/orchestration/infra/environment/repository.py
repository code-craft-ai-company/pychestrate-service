"""
.. module:: orchestration.infra.environment.repository
    :synopsis: CRUD helpers for environment rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.orchestration.infra.environment.models import (
    Environment,
    EnvironmentEventKind,
    EnvironmentHistory,
    EnvironmentState,
)


def insert_environment(
        *,
        db_session: DbSession,
        project_id: str,
        kind_name: str,
        name: str,
        attrs: Dict[str, Any],
        created_at: datetime
    ) -> Environment:
    row = Environment(
        environment_id=new_uuid(),
        project_id=project_id,
        kind_name=kind_name,
        name=name,
        state=EnvironmentState.ACTIVE,
        attrs=dict(attrs),
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        environment_id: str
    ) -> Optional[Environment]:
    rtnval = (
        db_session.query(Environment)
        .filter(Environment.environment_id == environment_id)
        .first()
    )
    return rtnval


def find_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        kind_name: str,
        name: str
    ) -> Optional[Environment]:
    rtnval = (
        db_session.query(Environment)
        .filter(Environment.project_id == project_id)
        .filter(Environment.kind_name == kind_name)
        .filter(Environment.name == name)
        .first()
    )
    return rtnval


def list_environments(
        *,
        db_session: DbSession,
        project_id: str,
        kind_name: Optional[str],
        state: Optional[EnvironmentState],
        limit: int
    ) -> List[Environment]:
    query = (
        db_session.query(Environment)
        .filter(Environment.project_id == project_id)
    )
    if kind_name is not None:
        query = query.filter(Environment.kind_name == kind_name)
    if state is not None:
        query = query.filter(Environment.state == state)
    rows = (
        query.order_by(
            Environment.kind_name.asc(), Environment.name.asc(),
        )
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_history_entry(
        *,
        db_session: DbSession,
        environment_id: str,
        event_kind: EnvironmentEventKind,
        actor_id: Optional[str],
        run_id: Optional[str],
        payload: Dict[str, Any],
        at_ts: datetime
    ) -> EnvironmentHistory:
    row = EnvironmentHistory(
        history_id=new_uuid(),
        environment_id=environment_id,
        event_kind=event_kind,
        actor_id=actor_id,
        run_id=run_id,
        payload=dict(payload),
        at_ts=at_ts,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_history_for_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        limit: int
    ) -> List[EnvironmentHistory]:
    rows = (
        db_session.query(EnvironmentHistory)
        .filter(EnvironmentHistory.environment_id == environment_id)
        .order_by(EnvironmentHistory.at_ts.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
