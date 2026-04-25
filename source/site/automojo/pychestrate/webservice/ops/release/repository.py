"""
.. module:: ops.release.repository
    :synopsis: CRUD helpers for release-channels rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.ops.release.models import (
    ChannelStateRow,
    ReleaseChannel,
    ReleaseComponent,
    ReleaseRow,
    ReleaseStageEvent,
    ReleaseStatus,
    StageEventKind,
)


def insert_release(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        version: str,
        channel: ReleaseChannel,
        artifact_uri: str,
        artifact_sha256: str,
        manifest_bytes: bytes,
        signature: bytes,
        issuer_key_id: str,
        issued_at: datetime,
        issued_by: Optional[str],
        rollout_fraction: float,
        previous_release_id: Optional[str]
    ) -> ReleaseRow:
    row = ReleaseRow(
        release_id=new_uuid(),
        component=component,
        version=version,
        channel=channel,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        manifest_bytes=manifest_bytes,
        signature=signature,
        issuer_key_id=issuer_key_id,
        issued_at=issued_at,
        issued_by=issued_by,
        status=ReleaseStatus.ACTIVE,
        rollout_fraction=rollout_fraction,
        stage_started_at=issued_at,
        previous_release_id=previous_release_id,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_release_by_id(
        *,
        db_session: DbSession,
        release_id: str
    ) -> Optional[ReleaseRow]:
    rtnval = (
        db_session.query(ReleaseRow)
        .filter(ReleaseRow.release_id == release_id)
        .first()
    )
    return rtnval


def find_release_by_triple(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        version: str,
        channel: ReleaseChannel
    ) -> Optional[ReleaseRow]:
    rtnval = (
        db_session.query(ReleaseRow)
        .filter(ReleaseRow.component == component)
        .filter(ReleaseRow.version == version)
        .filter(ReleaseRow.channel == channel)
        .first()
    )
    return rtnval


def list_releases(
        *,
        db_session: DbSession,
        component: Optional[ReleaseComponent] = None,
        channel: Optional[ReleaseChannel] = None,
        status: Optional[ReleaseStatus] = None
    ) -> List[ReleaseRow]:
    query = db_session.query(ReleaseRow)
    if component is not None:
        query = query.filter(ReleaseRow.component == component)
    if channel is not None:
        query = query.filter(ReleaseRow.channel == channel)
    if status is not None:
        query = query.filter(ReleaseRow.status == status)
    rows = query.order_by(ReleaseRow.issued_at.desc()).all()
    rtnval = list(rows)
    return rtnval


def upsert_channel_state(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        channel: ReleaseChannel,
        current_release_id: Optional[str],
        previous_release_id: Optional[str],
        last_promotion_at: Optional[datetime],
        last_rollback_at: Optional[datetime]
    ) -> ChannelStateRow:
    row = (
        db_session.query(ChannelStateRow)
        .filter(ChannelStateRow.component == component)
        .filter(ChannelStateRow.channel == channel)
        .first()
    )
    if row is None:
        row = ChannelStateRow(
            component=component,
            channel=channel,
            current_release_id=current_release_id,
            previous_release_id=previous_release_id,
            last_promotion_at=last_promotion_at,
            last_rollback_at=last_rollback_at,
        )
        db_session.add(row)
    else:
        row.current_release_id = current_release_id
        row.previous_release_id = previous_release_id
        if last_promotion_at is not None:
            row.last_promotion_at = last_promotion_at
        if last_rollback_at is not None:
            row.last_rollback_at = last_rollback_at
    db_session.flush()
    return row


def find_channel_state(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        channel: ReleaseChannel
    ) -> Optional[ChannelStateRow]:
    rtnval = (
        db_session.query(ChannelStateRow)
        .filter(ChannelStateRow.component == component)
        .filter(ChannelStateRow.channel == channel)
        .first()
    )
    return rtnval


def insert_stage_event(
        *,
        db_session: DbSession,
        release_id: str,
        kind: StageEventKind,
        from_fraction: Optional[float],
        to_fraction: Optional[float],
        reason: Optional[str],
        actor_user_id: Optional[str],
        occurred_at: datetime
    ) -> ReleaseStageEvent:
    row = ReleaseStageEvent(
        event_id=new_uuid(),
        release_id=release_id,
        kind=kind,
        from_fraction=from_fraction,
        to_fraction=to_fraction,
        reason=reason,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_stage_events_for_release(
        *,
        db_session: DbSession,
        release_id: str
    ) -> List[ReleaseStageEvent]:
    rows = (
        db_session.query(ReleaseStageEvent)
        .filter(ReleaseStageEvent.release_id == release_id)
        .order_by(ReleaseStageEvent.occurred_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
