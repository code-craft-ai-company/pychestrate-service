"""
.. module:: ops.release.release_service
    :synopsis: Release-channels service facade — publish on canary.

M1 ships :func:`publish_release` end-to-end on the canary
channel: build the canonical manifest, sign it, persist the
release row, update the channel-state pointer, append the
PUBLISHED stage-event, and emit ``entity.release.published`` +
``entity.release.canary_started``.

Promotion and rollback land in M2; the M1 entry points keep
the IO shapes stable so M2 can extend the surface without
rewriting callers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.ops.release import (
    manifest_signer,
    repository,
)
from automojo.pychestrate.webservice.ops.release.errors import (
    ReleaseConflictError,
)
from automojo.pychestrate.webservice.ops.release.events import (
    ReleaseEventTopics,
)
from automojo.pychestrate.webservice.ops.release.models import (
    ReleaseChannel,
    ReleaseComponent,
    ReleaseRow,
    ReleaseStatus,
    StageEventKind,
)
from automojo.pychestrate.webservice.ops.release.policy_router import (
    resolve_policy,
)
from automojo.pychestrate.webservice.ops.release.release_aspects import (
    ReleaseAspects,
)


@dataclass(frozen=True)
class ReleaseRecord:
    """
        Caller-facing release read-model.
    """
    release_id: str
    component: ReleaseComponent
    version: str
    channel: ReleaseChannel
    artifact_uri: str
    artifact_sha256: str
    manifest_bytes: bytes
    signature: bytes
    issuer_key_id: str
    issued_at: datetime
    issued_by: Optional[str]
    status: ReleaseStatus
    rollout_fraction: float
    stage_started_at: datetime
    previous_release_id: Optional[str]


def build_canonical_manifest(
        *,
        component: ReleaseComponent,
        version: str,
        channel: ReleaseChannel,
        artifact_uri: str,
        artifact_sha256: str,
        issued_at: datetime,
        issuer_key_id: str
    ) -> bytes:
    """
        Produce the canonical manifest bytes signed by the
        signer. The format is a deterministic JSON object with
        sorted keys so different processes serializing the
        same input produce identical bytes.
    """
    payload = {
        "component": component.value,
        "version": version,
        "channel": channel.value,
        "artifact_uri": artifact_uri,
        "artifact_sha256": artifact_sha256,
        "issued_at": issued_at.isoformat(),
        "issuer_key_id": issuer_key_id,
    }
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return rtnval


def publish_release(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        version: str,
        channel: ReleaseChannel,
        artifact_uri: str,
        artifact_sha256: str,
        aspects: ReleaseAspects,
        actor_id: Optional[str] = None
    ) -> ReleaseRecord:
    """
        Publish a release on ``channel`` at the channel
        policy's initial fraction. Returns the read-model.

        :raises: ReleaseConflictError on a duplicate
                 ``(component, version, channel)`` triple.
    """
    if version is None or len(version) == 0:
        err_lines = ["Release version must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if artifact_sha256 is None or len(artifact_sha256) != 64:
        err_lines = [
            "Release artifact_sha256 must be a 64-character hex digest.",
        ]
        err_lines.append("VALUE: {!r}".format(artifact_sha256))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    existing = repository.find_release_by_triple(
        db_session=db_session,
        component=component,
        version=version,
        channel=channel,
    )
    if existing is not None:
        err_lines = ["Release triple already exists on the ledger."]
        err_lines.append("COMPONENT: {}".format(component.value))
        err_lines.append("VERSION: {}".format(version))
        err_lines.append("CHANNEL: {}".format(channel.value))
        err_msg = os.linesep.join(err_lines)
        raise ReleaseConflictError(err_msg) from None

    active_key = manifest_signer.get_active_signing_key()
    issued_at = utc_now()
    manifest_bytes = build_canonical_manifest(
        component=component,
        version=version,
        channel=channel,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        issued_at=issued_at,
        issuer_key_id=active_key.issuer_key_id,
    )
    signature = manifest_signer.sign_manifest(
        manifest_bytes=manifest_bytes,
        issuer_key_id=active_key.issuer_key_id,
    )

    policy_cls = resolve_policy(channel=channel)
    initial_fraction = policy_cls.initial_fraction(channel=channel)

    state = repository.find_channel_state(
        db_session=db_session, component=component, channel=channel,
    )
    previous_release_id = (
        state.current_release_id if state is not None else None
    )

    row = repository.insert_release(
        db_session=db_session,
        component=component,
        version=version,
        channel=channel,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        manifest_bytes=manifest_bytes,
        signature=signature,
        issuer_key_id=active_key.issuer_key_id,
        issued_at=issued_at,
        issued_by=actor_id,
        rollout_fraction=initial_fraction,
        previous_release_id=(
            str(previous_release_id) if previous_release_id is not None
            else None
        ),
    )
    repository.upsert_channel_state(
        db_session=db_session,
        component=component,
        channel=channel,
        current_release_id=str(row.release_id),
        previous_release_id=(
            str(previous_release_id) if previous_release_id is not None
            else None
        ),
        last_promotion_at=issued_at,
        last_rollback_at=None,
    )
    repository.insert_stage_event(
        db_session=db_session,
        release_id=str(row.release_id),
        kind=StageEventKind.PUBLISHED,
        from_fraction=None,
        to_fraction=initial_fraction,
        reason=None,
        actor_user_id=actor_id,
        occurred_at=issued_at,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ReleaseEventTopics.PUBLISHED,
            payload={
                "release_id": str(row.release_id),
                "component": component.value,
                "channel": channel.value,
                "version": version,
                "artifact_sha256": artifact_sha256,
                "issuer_key_id": active_key.issuer_key_id,
                "issued_at": issued_at.isoformat(),
                "issued_by": actor_id,
                "rollout_fraction": initial_fraction,
            },
            source_event_id=new_uuid(),
        ),
    )
    if channel == ReleaseChannel.CANARY:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ReleaseEventTopics.CANARY_STARTED,
                payload={
                    "release_id": str(row.release_id),
                    "component": component.value,
                    "channel": channel.value,
                    "fraction": initial_fraction,
                    "at": issued_at.isoformat(),
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    rtnval = _row_to_record(row=row)
    return rtnval


def get_release(
        *,
        db_session: DbSession,
        release_id: str
    ) -> Optional[ReleaseRecord]:
    """
        Read by id.
    """
    row = repository.find_release_by_id(
        db_session=db_session, release_id=release_id,
    )
    if row is None:
        return None
    rtnval = _row_to_record(row=row)
    return rtnval


def list_releases(
        *,
        db_session: DbSession,
        component: Optional[ReleaseComponent] = None,
        channel: Optional[ReleaseChannel] = None,
        status: Optional[ReleaseStatus] = None
    ) -> List[ReleaseRecord]:
    """
        List releases newest-first.
    """
    rows = repository.list_releases(
        db_session=db_session,
        component=component,
        channel=channel,
        status=status,
    )
    rtnval = [_row_to_record(row=r) for r in rows]
    return rtnval


def get_current_manifest(
        *,
        db_session: DbSession,
        component: ReleaseComponent,
        channel: ReleaseChannel
    ) -> Optional[ReleaseRecord]:
    """
        Return the release currently advertised on the
        ``(component, channel)`` pair, or ``None`` when no
        release has been published yet.
    """
    state = repository.find_channel_state(
        db_session=db_session, component=component, channel=channel,
    )
    if state is None or state.current_release_id is None:
        return None
    row = repository.find_release_by_id(
        db_session=db_session,
        release_id=str(state.current_release_id),
    )
    if row is None:
        return None
    rtnval = _row_to_record(row=row)
    return rtnval


def _row_to_record(*, row: ReleaseRow) -> ReleaseRecord:
    rtnval = ReleaseRecord(
        release_id=str(row.release_id),
        component=row.component,
        version=row.version,
        channel=row.channel,
        artifact_uri=row.artifact_uri,
        artifact_sha256=row.artifact_sha256,
        manifest_bytes=bytes(row.manifest_bytes),
        signature=bytes(row.signature),
        issuer_key_id=row.issuer_key_id,
        issued_at=row.issued_at,
        issued_by=(
            str(row.issued_by) if row.issued_by is not None else None
        ),
        status=row.status,
        rollout_fraction=row.rollout_fraction,
        stage_started_at=row.stage_started_at,
        previous_release_id=(
            str(row.previous_release_id)
            if row.previous_release_id is not None
            else None
        ),
    )
    return rtnval
