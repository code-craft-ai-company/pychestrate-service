"""
.. module:: orchestration.infra.runs.repository
    :synopsis: CRUD helpers for infra-run rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
    InfraRun,
    InfraRunState,
)


def insert_infra_run(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        driver_name: str,
        action: InfraAction,
        actor_id: Optional[str],
        actor_role_set_csv: str,
        inputs: Dict[str, Any],
        inputs_canonical_sha256: str,
        replay_of: Optional[str],
        started_at: datetime
    ) -> InfraRun:
    row = InfraRun(
        run_id=new_uuid(),
        project_id=project_id,
        environment_id=environment_id,
        driver_name=driver_name,
        action=action,
        state=InfraRunState.PENDING,
        actor_id=actor_id,
        actor_role_set_csv=actor_role_set_csv,
        inputs=dict(inputs),
        inputs_canonical_sha256=inputs_canonical_sha256,
        replay_of=replay_of,
        started_at=started_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_run_by_id(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[InfraRun]:
    rtnval = (
        db_session.query(InfraRun)
        .filter(InfraRun.run_id == run_id)
        .first()
    )
    return rtnval


def list_runs_for_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        limit: int
    ) -> List[InfraRun]:
    rows = (
        db_session.query(InfraRun)
        .filter(InfraRun.environment_id == environment_id)
        .order_by(InfraRun.started_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
