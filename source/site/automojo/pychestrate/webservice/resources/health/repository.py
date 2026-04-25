"""
.. module:: resources.health.repository
    :synopsis: CRUD helpers for resource-health rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.resources.health.models import (
    ProbeOutcome,
    ResourceHealth,
)


def insert_health_record(
        *,
        db_session: DbSession,
        resource_id: str,
        project_id: str,
        probe_name: str,
        probe_period_seconds: int,
        next_probe_at: datetime
    ) -> ResourceHealth:
    row = ResourceHealth(
        health_id=new_uuid(),
        resource_id=resource_id,
        project_id=project_id,
        probe_name=probe_name,
        probe_period_seconds=probe_period_seconds,
        last_outcome=ProbeOutcome.UNKNOWN,
        last_probe_at=None,
        last_pass_at=None,
        last_fail_at=None,
        next_probe_at=next_probe_at,
        pass_count=0,
        fail_count=0,
        consecutive_failures=0,
        last_error=None,
        last_payload={},
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        health_id: str
    ) -> Optional[ResourceHealth]:
    rtnval = (
        db_session.query(ResourceHealth)
        .filter(ResourceHealth.health_id == health_id)
        .first()
    )
    return rtnval


def find_by_resource(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> Optional[ResourceHealth]:
    rtnval = (
        db_session.query(ResourceHealth)
        .filter(ResourceHealth.resource_id == resource_id)
        .first()
    )
    return rtnval


def list_due_for_probe(
        *,
        db_session: DbSession,
        when: datetime,
        limit: int
    ) -> List[ResourceHealth]:
    rows = (
        db_session.query(ResourceHealth)
        .filter(ResourceHealth.next_probe_at <= when)
        .order_by(ResourceHealth.next_probe_at.asc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete_health_record(
        *,
        db_session: DbSession,
        row: ResourceHealth
    ) -> None:
    db_session.delete(row)
    db_session.flush()
    return
