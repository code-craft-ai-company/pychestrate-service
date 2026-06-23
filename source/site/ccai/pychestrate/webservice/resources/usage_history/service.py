"""
.. module:: resources.usage_history.service
    :synopsis: Usage-history facade — append / list / get.

M1 ships the persistence-only surface: :func:`append_event` is
the single entry point for translating a bus event into a
timeline row and is built to be idempotent under retried
delivery. The bus subscribers and the M2 hook pipeline land on
top of this module without changing the caller contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.usage_history import repository
from ccai.pychestrate.webservice.resources.usage_history.errors import (
    TimelineEventNotFoundError,
)
from ccai.pychestrate.webservice.resources.usage_history.events import (
    UsageHistoryEventTopics,
)
from ccai.pychestrate.webservice.resources.usage_history.models import (
    ResourceTimelineEvent,
    UsageEventType,
)


DEFAULT_TIMELINE_LIMIT: int = 200


@dataclass(frozen=True)
class TimelineEventView:
    """
        Caller-facing read-model for a timeline row.
    """
    event_id: str
    source_event_id: str
    resource_id: str
    project_id: str
    event_type: UsageEventType
    actor_id: Optional[str]
    pod_event_group_id: Optional[str]
    at_ts: datetime
    payload: Dict[str, Any] = field(default_factory=dict)
    annotations: Dict[str, Any] = field(default_factory=dict)


def append_event(
        *,
        db_session: DbSession,
        source_event_id: str,
        resource_id: str,
        project_id: str,
        event_type: UsageEventType,
        at_ts: Optional[datetime] = None,
        actor_id: Optional[str] = None,
        pod_event_group_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        annotations: Optional[Dict[str, Any]] = None
    ) -> TimelineEventView:
    """
        Append one timeline row. Idempotent on the
        ``(source_event_id, resource_id)`` pair — a duplicate
        call returns the existing view and emits
        :data:`UsageHistoryEventTopics.DUPLICATE_SUPPRESSED`
        instead of inserting a new row.
    """
    existing = repository.find_by_source_and_resource(
        db_session=db_session,
        source_event_id=source_event_id,
        resource_id=resource_id,
    )
    if existing is not None:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=UsageHistoryEventTopics.DUPLICATE_SUPPRESSED,
                payload={
                    "event_id": str(existing.event_id),
                    "source_event_id": source_event_id,
                    "resource_id": resource_id,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        rtnval = _to_view(row=existing)
        return rtnval

    when = at_ts if at_ts is not None else utc_now()
    effective_payload = dict(payload or {})
    effective_annotations = dict(annotations or {})
    row = repository.insert_event(
        db_session=db_session,
        source_event_id=source_event_id,
        resource_id=resource_id,
        project_id=project_id,
        event_type=event_type,
        at_ts=when,
        actor_id=actor_id,
        pod_event_group_id=pod_event_group_id,
        payload=effective_payload,
        annotations=effective_annotations,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UsageHistoryEventTopics.APPENDED,
            payload={
                "event_id": str(row.event_id),
                "source_event_id": source_event_id,
                "resource_id": resource_id,
                "project_id": project_id,
                "event_type": event_type.value,
                "at_ts": when.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def list_timeline(
        *,
        db_session: DbSession,
        resource_id: str,
        limit: int = DEFAULT_TIMELINE_LIMIT
    ) -> List[TimelineEventView]:
    """
        Return ``limit`` most-recent timeline rows for
        ``resource_id`` ordered newest first.
    """
    rows = repository.list_for_resource(
        db_session=db_session, resource_id=resource_id, limit=limit,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def get_event(
        *,
        db_session: DbSession,
        event_id: str
    ) -> TimelineEventView:
    """
        Read a single timeline row.

        :raises: TimelineEventNotFoundError on miss.
    """
    row = repository.find_by_id(db_session=db_session, event_id=event_id)
    if row is None:
        err_lines = ["Timeline event not found."]
        err_lines.append("EVENT_ID: {}".format(event_id))
        err_msg = os.linesep.join(err_lines)
        raise TimelineEventNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def _to_view(*, row: ResourceTimelineEvent) -> TimelineEventView:
    rtnval = TimelineEventView(
        event_id=str(row.event_id),
        source_event_id=str(row.source_event_id),
        resource_id=str(row.resource_id),
        project_id=str(row.project_id),
        event_type=row.event_type,
        actor_id=str(row.actor_id) if row.actor_id is not None else None,
        pod_event_group_id=(
            str(row.pod_event_group_id) if row.pod_event_group_id is not None else None
        ),
        at_ts=row.at_ts,
        payload=dict(row.payload or {}),
        annotations=dict(row.annotations or {}),
    )
    return rtnval
