"""
.. module:: metrics.slos.repository
    :synopsis: CRUD helpers for SLO + burn-rate-state rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.metrics.slos.models import (
    SLO,
    SLOBurnRateState,
)


def insert_slo(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str,
        kind: str,
        target: float,
        window_seconds: int,
        definition_config: Dict[str, Any],
        default_notification_route_key: Optional[str],
        auto_attach_burn_rate_alerts: bool,
        created_at: datetime
    ) -> SLO:
    row = SLO(
        slo_id=new_uuid(),
        project_id=project_id,
        name=name,
        description=description,
        kind=kind,
        target=target,
        window_seconds=window_seconds,
        definition_config=dict(definition_config),
        default_notification_route_key=default_notification_route_key,
        auto_attach_burn_rate_alerts=auto_attach_burn_rate_alerts,
        version=1,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        slo_id: str
    ) -> Optional[SLO]:
    rtnval = (
        db_session.query(SLO)
        .filter(SLO.slo_id == slo_id)
        .first()
    )
    return rtnval


def find_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[SLO]:
    rtnval = (
        db_session.query(SLO)
        .filter(SLO.project_id == project_id)
        .filter(SLO.name == name)
        .first()
    )
    return rtnval


def list_for_project(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[SLO]:
    rows = (
        db_session.query(SLO)
        .filter(SLO.project_id == project_id)
        .order_by(SLO.name.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete_slo_row(
        *,
        db_session: DbSession,
        row: SLO
    ) -> None:
    db_session.delete(row)
    db_session.flush()
    return


def find_burn_rate_state(
        *,
        db_session: DbSession,
        slo_id: str
    ) -> Optional[SLOBurnRateState]:
    rtnval = (
        db_session.query(SLOBurnRateState)
        .filter(SLOBurnRateState.slo_id == slo_id)
        .first()
    )
    return rtnval
