"""
.. module:: orchestration.build.artifacts.service
    :synopsis: Build-artifacts facade — synthesize / read / promote.

M1 ships:

* :func:`synthesize_manifest` — append-only manifest insert
  keyed on ``build_run_id`` (UNIQUE). Validates every entry's
  payload through the registered artifact-type's
  ``validate_payload``. Idempotent on duplicate calls — the
  existing manifest is returned without re-emit.
* :func:`get_manifest` / :func:`list_entries`.
* :func:`promote_to_channel` — append a PROMOTE row to the
  ledger and upsert the channel-head pointer. Emits PROMOTED
  + CHANNEL_HEAD_ADVANCED.
* :func:`get_channel_head`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.build.artifacts import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.errors import (
    ArtifactEntryInvalidError,
    ArtifactTypeUnknownError,
    BuildArtifactManifestNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.events import (
    BuildArtifactEventTopics,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.factories.artifact_type_protocol import (
    ArtifactTypeProtocol,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.models import (
    BuildArtifactEntryIndex,
    BuildArtifactManifest,
    ChannelHead,
    PromotionAction,
)


BUILD_ARTIFACT_TYPE_PROTOCOL: str = "build_artifact_type"


@dataclass(frozen=True)
class ArtifactEntry:
    """
        Caller-supplied artifact entry.

        :param artifact_id: Caller-stable identifier; unique
                            within a manifest.
        :param artifact_type: Registered
                              :class:`ArtifactTypeProtocol`
                              name.
        :param artifact_name: Human-friendly name.
        :param storage_uri: Where the bytes live (object-store
                            URI; M2 wires real fetching).
        :param sha256: 64-char hex digest of the artifact bytes.
        :param payload: Type-specific metadata. Schema is
                        validated by the artifact type.
    """
    artifact_id: str
    artifact_type: str
    artifact_name: str
    storage_uri: str
    sha256: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactEntryView:
    """
        Caller-facing read-model for a manifest entry.
    """
    manifest_id: str
    artifact_id: str
    artifact_type: str
    artifact_name: str
    storage_uri: str
    sha256: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManifestView:
    """
        Caller-facing manifest read-model.
    """
    manifest_id: str
    project_id: str
    build_run_id: str
    entry_count: int
    note: str
    synthesized_at: datetime
    entries: Tuple[ArtifactEntryView, ...] = ()


@dataclass(frozen=True)
class ChannelHeadView:
    """
        Caller-facing channel-head read-model.
    """
    project_id: str
    channel: str
    artifact_id: str
    manifest_id: str
    promoted_at: datetime


def synthesize_manifest(
        *,
        db_session: DbSession,
        project_id: str,
        build_run_id: str,
        entries: List[ArtifactEntry],
        note: str = ""
    ) -> ManifestView:
    """
        Insert a fresh manifest. Validates every entry's
        payload against its registered artifact type, then
        persists the manifest + entries + emits
        :data:`BuildArtifactEventTopics.MANIFEST_SYNTHESIZED`.

        Idempotent on duplicate ``build_run_id`` — the
        existing manifest is returned.

        :raises: ArtifactTypeUnknownError when an entry
                 references an unregistered type.
        :raises: ArtifactEntryInvalidError when a type's
                 ``validate_payload`` rejects an entry.
    """
    existing = repository.find_manifest_by_build_run(
        db_session=db_session, build_run_id=build_run_id,
    )
    if existing is not None:
        rtnval = _to_manifest_view(
            row=existing,
            entries=repository.list_entries_for_manifest(
                db_session=db_session,
                manifest_id=str(existing.manifest_id),
            ),
        )
        return rtnval

    type_index = _resolve_type_index()
    issues: List[str] = []
    seen_ids: List[str] = []
    for index, entry in enumerate(entries):
        if entry.artifact_id in seen_ids:
            issues.append(
                "entries[{}].artifact_id duplicate: '{}'".format(
                    index, entry.artifact_id,
                ),
            )
        seen_ids.append(entry.artifact_id)
        type_cls = type_index.get(entry.artifact_type, None)
        if type_cls is None:
            err_lines = ["Artifact references an unknown artifact_type."]
            err_lines.append("ARTIFACT_ID: {}".format(entry.artifact_id))
            err_lines.append("ARTIFACT_TYPE: {}".format(entry.artifact_type))
            err_lines.append("REGISTERED: {}".format(
                ", ".join(sorted(type_index.keys())),
            ))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactTypeUnknownError(err_msg) from None
        ok, kind_issues = type_cls.validate_payload(payload=entry.payload)
        if ok is False:
            for issue in kind_issues:
                issues.append(
                    "entries[{}] '{}': {}".format(
                        index, entry.artifact_id, issue,
                    )
                )
        if not isinstance(entry.sha256, str) or len(entry.sha256) != 64:
            issues.append(
                "entries[{}] '{}'.sha256 must be 64 hex chars".format(
                    index, entry.artifact_id,
                )
            )

    if len(issues) > 0:
        err_lines = [
            "Manifest synthesis failed: {} entry issue(s).".format(
                len(issues),
            ),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactEntryInvalidError(err_msg) from None

    now = utc_now()
    manifest_row = repository.insert_manifest(
        db_session=db_session,
        project_id=project_id,
        build_run_id=build_run_id,
        entry_count=len(entries),
        note=note,
        synthesized_at=now,
    )
    entry_rows: List[BuildArtifactEntryIndex] = []
    for entry in entries:
        entry_row = repository.insert_entry(
            db_session=db_session,
            manifest_id=str(manifest_row.manifest_id),
            artifact_id=entry.artifact_id,
            artifact_type=entry.artifact_type,
            artifact_name=entry.artifact_name,
            storage_uri=entry.storage_uri,
            sha256=entry.sha256,
            payload=dict(entry.payload),
        )
        entry_rows.append(entry_row)

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildArtifactEventTopics.MANIFEST_SYNTHESIZED,
            payload={
                "manifest_id": str(manifest_row.manifest_id),
                "project_id": project_id,
                "build_run_id": build_run_id,
                "entry_count": len(entries),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_manifest_view(row=manifest_row, entries=entry_rows)
    return rtnval


def get_manifest(
        *,
        db_session: DbSession,
        manifest_id: str
    ) -> ManifestView:
    """
        Read a manifest + its entries.

        :raises: BuildArtifactManifestNotFoundError on miss.
    """
    row = repository.find_manifest_by_id(
        db_session=db_session, manifest_id=manifest_id,
    )
    if row is None:
        err_lines = ["Manifest not found."]
        err_lines.append("MANIFEST_ID: {}".format(manifest_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildArtifactManifestNotFoundError(err_msg) from None
    entries = repository.list_entries_for_manifest(
        db_session=db_session, manifest_id=manifest_id,
    )
    rtnval = _to_manifest_view(row=row, entries=entries)
    return rtnval


def list_entries(
        *,
        db_session: DbSession,
        manifest_id: str
    ) -> List[ArtifactEntryView]:
    """
        Return every entry on a manifest in stable order.
    """
    rows = repository.list_entries_for_manifest(
        db_session=db_session, manifest_id=manifest_id,
    )
    rtnval = [_to_entry_view(row=r) for r in rows]
    return rtnval


def promote_to_channel(
        *,
        db_session: DbSession,
        project_id: str,
        manifest_id: str,
        artifact_id: str,
        channel: str,
        actor_id: Optional[str] = None,
        note: str = ""
    ) -> ChannelHeadView:
    """
        Append a PROMOTE row to the ledger and advance the
        channel-head pointer. Idempotent on a re-promote of the
        same (manifest, artifact, channel) tuple — the head is
        already at the requested manifest. Emits PROMOTED +
        CHANNEL_HEAD_ADVANCED.

        :raises: BuildArtifactManifestNotFoundError when the
                 manifest does not exist.
        :raises: ArtifactEntryInvalidError when the manifest
                 has no entry with ``artifact_id``.
    """
    manifest = repository.find_manifest_by_id(
        db_session=db_session, manifest_id=manifest_id,
    )
    if manifest is None:
        err_lines = ["Manifest not found."]
        err_lines.append("MANIFEST_ID: {}".format(manifest_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildArtifactManifestNotFoundError(err_msg) from None
    if str(manifest.project_id) != project_id:
        err_lines = ["Manifest project mismatch."]
        err_lines.append("MANIFEST_ID: {}".format(manifest_id))
        err_lines.append("EXPECTED_PROJECT: {}".format(project_id))
        err_lines.append("ACTUAL_PROJECT: {}".format(manifest.project_id))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactEntryInvalidError(err_msg) from None

    entry = repository.find_entry(
        db_session=db_session, manifest_id=manifest_id,
        artifact_id=artifact_id,
    )
    if entry is None:
        err_lines = ["Manifest does not contain the requested artifact."]
        err_lines.append("MANIFEST_ID: {}".format(manifest_id))
        err_lines.append("ARTIFACT_ID: {}".format(artifact_id))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactEntryInvalidError(err_msg) from None

    now = utc_now()
    repository.insert_ledger_entry(
        db_session=db_session,
        project_id=project_id,
        manifest_id=manifest_id,
        artifact_id=artifact_id,
        channel=channel,
        action=PromotionAction.PROMOTE,
        actor_id=actor_id,
        note=note,
        at_ts=now,
    )
    head = repository.upsert_channel_head(
        db_session=db_session,
        project_id=project_id,
        channel=channel,
        artifact_id=artifact_id,
        manifest_id=manifest_id,
        promoted_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildArtifactEventTopics.PROMOTED,
            payload={
                "project_id": project_id,
                "manifest_id": manifest_id,
                "artifact_id": artifact_id,
                "channel": channel,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildArtifactEventTopics.CHANNEL_HEAD_ADVANCED,
            payload={
                "project_id": project_id,
                "channel": channel,
                "artifact_id": artifact_id,
                "manifest_id": manifest_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_channel_head_view(row=head)
    return rtnval


def get_channel_head(
        *,
        db_session: DbSession,
        project_id: str,
        channel: str,
        artifact_id: str
    ) -> Optional[ChannelHeadView]:
    """
        Return the (project, channel, artifact) head pointer or
        ``None`` if nothing has been promoted yet.
    """
    row = repository.find_channel_head(
        db_session=db_session,
        project_id=project_id,
        channel=channel,
        artifact_id=artifact_id,
    )
    if row is None:
        return None
    rtnval = _to_channel_head_view(row=row)
    return rtnval


def _resolve_type_index():
    candidates = list_factory_implementations(
        factory_protocol_name=BUILD_ARTIFACT_TYPE_PROTOCOL,
    )
    rtnval = {impl.artifact_type_name(): impl for impl in candidates}
    return rtnval


def _to_entry_view(*, row: BuildArtifactEntryIndex) -> ArtifactEntryView:
    rtnval = ArtifactEntryView(
        manifest_id=str(row.manifest_id),
        artifact_id=row.artifact_id,
        artifact_type=row.artifact_type,
        artifact_name=row.artifact_name,
        storage_uri=row.storage_uri,
        sha256=row.sha256,
        payload=dict(row.payload or {}),
    )
    return rtnval


def _to_manifest_view(
        *,
        row: BuildArtifactManifest,
        entries: List[BuildArtifactEntryIndex]
    ) -> ManifestView:
    entry_views = tuple(_to_entry_view(row=e) for e in entries)
    rtnval = ManifestView(
        manifest_id=str(row.manifest_id),
        project_id=str(row.project_id),
        build_run_id=str(row.build_run_id),
        entry_count=row.entry_count,
        note=row.note,
        synthesized_at=row.synthesized_at,
        entries=entry_views,
    )
    return rtnval


def _to_channel_head_view(*, row: ChannelHead) -> ChannelHeadView:
    rtnval = ChannelHeadView(
        project_id=str(row.project_id),
        channel=row.channel,
        artifact_id=row.artifact_id,
        manifest_id=str(row.manifest_id),
        promoted_at=row.promoted_at,
    )
    return rtnval
