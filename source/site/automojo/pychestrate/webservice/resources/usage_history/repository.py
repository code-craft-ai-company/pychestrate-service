"""
.. module:: resources.usage_history.repository
    :synopsis: CRUD helpers for resource timeline rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.resources.usage_history.models import (
    ResourceTimelineEvent,
    UsageEventType,
)


def insert_event(
        *,
        db_session: DbSession,
        source_event_id: str,
        resource_id: str,
        project_id: str,
        event_type: UsageEventType,
        at_ts: datetime,
        actor_id: Optional[str],
        pod_event_group_id: Optional[str],
        payload: Dict[str, Any],
        annotations: Dict[str, Any]
    ) -> ResourceTimelineEvent:
    row = ResourceTimelineEvent(
        event_id=new_uuid(),
        source_event_id=source_event_id,
        resource_id=resource_id,
        project_id=project_id,
        event_type=event_type,
        actor_id=actor_id,
        pod_event_group_id=pod_event_group_id,
        at_ts=at_ts,
        payload=dict(payload),
        annotations=dict(annotations),
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_id(
        *,
        db_session: DbSession,
        event_id: str
    ) -> Optional[ResourceTimelineEvent]:
    rtnval = (
        db_session.query(ResourceTimelineEvent)
        .filter(ResourceTimelineEvent.event_id == event_id)
        .first()
    )
    return rtnval


def find_by_source_and_resource(
        *,
        db_session: DbSession,
        source_event_id: str,
        resource_id: str
    ) -> Optional[ResourceTimelineEvent]:
    rtnval = (
        db_session.query(ResourceTimelineEvent)
        .filter(ResourceTimelineEvent.source_event_id == source_event_id)
        .filter(ResourceTimelineEvent.resource_id == resource_id)
        .first()
    )
    return rtnval


def list_for_resource(
        *,
        db_session: DbSession,
        resource_id: str,
        limit: int
    ) -> List[ResourceTimelineEvent]:
    rows = (
        db_session.query(ResourceTimelineEvent)
        .filter(ResourceTimelineEvent.resource_id == resource_id)
        .order_by(
            ResourceTimelineEvent.at_ts.desc(),
            ResourceTimelineEvent.event_id.desc(),
        )
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
