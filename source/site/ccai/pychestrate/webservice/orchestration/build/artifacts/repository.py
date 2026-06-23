"""
.. module:: orchestration.build.artifacts.repository
    :synopsis: CRUD helpers for build-artifacts rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.build.artifacts.models import (
    BuildArtifactEntryIndex,
    BuildArtifactManifest,
    BuildArtifactPromotionLedger,
    ChannelHead,
    PromotionAction,
)


def insert_manifest(
        *,
        db_session: DbSession,
        project_id: str,
        build_run_id: str,
        entry_count: int,
        note: str,
        synthesized_at: datetime
    ) -> BuildArtifactManifest:
    row = BuildArtifactManifest(
        manifest_id=new_uuid(),
        project_id=project_id,
        build_run_id=build_run_id,
        entry_count=entry_count,
        note=note,
        synthesized_at=synthesized_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_entry(
        *,
        db_session: DbSession,
        manifest_id: str,
        artifact_id: str,
        artifact_type: str,
        artifact_name: str,
        storage_uri: str,
        sha256: str,
        payload: Dict[str, Any]
    ) -> BuildArtifactEntryIndex:
    row = BuildArtifactEntryIndex(
        manifest_id=manifest_id,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        artifact_name=artifact_name,
        storage_uri=storage_uri,
        sha256=sha256,
        payload=dict(payload),
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_manifest_by_id(
        *,
        db_session: DbSession,
        manifest_id: str
    ) -> Optional[BuildArtifactManifest]:
    rtnval = (
        db_session.query(BuildArtifactManifest)
        .filter(BuildArtifactManifest.manifest_id == manifest_id)
        .first()
    )
    return rtnval


def find_manifest_by_build_run(
        *,
        db_session: DbSession,
        build_run_id: str
    ) -> Optional[BuildArtifactManifest]:
    rtnval = (
        db_session.query(BuildArtifactManifest)
        .filter(BuildArtifactManifest.build_run_id == build_run_id)
        .first()
    )
    return rtnval


def list_entries_for_manifest(
        *,
        db_session: DbSession,
        manifest_id: str
    ) -> List[BuildArtifactEntryIndex]:
    rows = (
        db_session.query(BuildArtifactEntryIndex)
        .filter(BuildArtifactEntryIndex.manifest_id == manifest_id)
        .order_by(BuildArtifactEntryIndex.artifact_id.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_entry(
        *,
        db_session: DbSession,
        manifest_id: str,
        artifact_id: str
    ) -> Optional[BuildArtifactEntryIndex]:
    rtnval = (
        db_session.query(BuildArtifactEntryIndex)
        .filter(BuildArtifactEntryIndex.manifest_id == manifest_id)
        .filter(BuildArtifactEntryIndex.artifact_id == artifact_id)
        .first()
    )
    return rtnval


def insert_ledger_entry(
        *,
        db_session: DbSession,
        project_id: str,
        manifest_id: str,
        artifact_id: str,
        channel: str,
        action: PromotionAction,
        actor_id: Optional[str],
        note: str,
        at_ts: datetime
    ) -> BuildArtifactPromotionLedger:
    row = BuildArtifactPromotionLedger(
        ledger_id=new_uuid(),
        project_id=project_id,
        manifest_id=manifest_id,
        artifact_id=artifact_id,
        channel=channel,
        action=action,
        actor_id=actor_id,
        note=note,
        at_ts=at_ts,
    )
    db_session.add(row)
    db_session.flush()
    return row


def upsert_channel_head(
        *,
        db_session: DbSession,
        project_id: str,
        channel: str,
        artifact_id: str,
        manifest_id: str,
        promoted_at: datetime
    ) -> ChannelHead:
    row = (
        db_session.query(ChannelHead)
        .filter(ChannelHead.project_id == project_id)
        .filter(ChannelHead.channel == channel)
        .filter(ChannelHead.artifact_id == artifact_id)
        .first()
    )
    if row is None:
        row = ChannelHead(
            project_id=project_id,
            channel=channel,
            artifact_id=artifact_id,
            manifest_id=manifest_id,
            promoted_at=promoted_at,
        )
        db_session.add(row)
    else:
        row.manifest_id = manifest_id
        row.promoted_at = promoted_at
    db_session.flush()
    return row


def find_channel_head(
        *,
        db_session: DbSession,
        project_id: str,
        channel: str,
        artifact_id: str
    ) -> Optional[ChannelHead]:
    rtnval = (
        db_session.query(ChannelHead)
        .filter(ChannelHead.project_id == project_id)
        .filter(ChannelHead.channel == channel)
        .filter(ChannelHead.artifact_id == artifact_id)
        .first()
    )
    return rtnval
