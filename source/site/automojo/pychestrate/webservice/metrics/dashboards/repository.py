"""
.. module:: metrics.dashboards.repository
    :synopsis: CRUD helpers for dashboard rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.metrics.dashboards.models import (
    Dashboard,
)


def insert_dashboard(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str,
        owner_principal_id: Optional[str],
        grid_columns_max: int,
        tiles: List[Dict[str, Any]],
        created_at: datetime
    ) -> Dashboard:
    row = Dashboard(
        dashboard_id=new_uuid(),
        project_id=project_id,
        name=name,
        description=description,
        owner_principal_id=owner_principal_id,
        grid_columns_max=grid_columns_max,
        tiles=list(tiles),
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
        dashboard_id: str
    ) -> Optional[Dashboard]:
    rtnval = (
        db_session.query(Dashboard)
        .filter(Dashboard.dashboard_id == dashboard_id)
        .first()
    )
    return rtnval


def find_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[Dashboard]:
    rtnval = (
        db_session.query(Dashboard)
        .filter(Dashboard.project_id == project_id)
        .filter(Dashboard.name == name)
        .first()
    )
    return rtnval


def list_for_project(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[Dashboard]:
    rows = (
        db_session.query(Dashboard)
        .filter(Dashboard.project_id == project_id)
        .order_by(Dashboard.name.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete_dashboard_row(
        *,
        db_session: DbSession,
        row: Dashboard
    ) -> None:
    db_session.delete(row)
    db_session.flush()
    return
