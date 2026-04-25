"""
.. module:: clients.upgrades.service
    :synopsis: Agent-upgrade-channel service facade.

M1 ships:

* :func:`draft_rollout` — persist a DRAFT row, look up the
  artifact source, store its descriptor, emit DRAFTED.
* :func:`start_rollout` — single-stage path: resolve the
  policy, compute the offer set, persist offer rows, and emit
  STARTED + STAGE_STARTED + per-offer OFFERED. The pin map is
  consulted before any offer is written so pinned pods are
  silently skipped.
* :func:`record_offer_outcome` — terminal-outcome ingestion;
  updates the offer row + stage counters and emits
  SUCCEEDED / FAILED / DEFERRED / INTEGRITY_FAILED.
* Read helpers + read-models.

Promote / halt / resume + multi-stage orchestration land in
M2; the M1 entry points are shaped so the M2 dispatcher can
extend the surface without rewriting callers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.clients.upgrades import (
    pins,
    repository,
)
from automojo.pychestrate.webservice.clients.upgrades.dtos import (
    ArtifactDescriptor,
    FleetSnapshot,
)
from automojo.pychestrate.webservice.clients.upgrades.enums import (
    OfferOutcome,
    RolloutState,
    StageState,
)
from automojo.pychestrate.webservice.clients.upgrades.errors import (
    InvalidRolloutTransitionError,
    RolloutNotFoundError,
)
from automojo.pychestrate.webservice.clients.upgrades.events import (
    UpgradeEventTopics,
)
from automojo.pychestrate.webservice.clients.upgrades.factories.rollout_policy_protocol import (
    RolloutPolicyProtocol,
)
from automojo.pychestrate.webservice.clients.upgrades.factories.upgrade_artifact_source_protocol import (
    UpgradeArtifactSourceProtocol,
)
from automojo.pychestrate.webservice.clients.upgrades.models import (
    AgentRollout,
    AgentRolloutStage,
    AgentUpgradeOffer,
)
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


@dataclass(frozen=True)
class RolloutRecord:
    """
        Caller-facing rollout read-model.
    """
    rollout_id: str
    version: str
    artifact_source: str
    artifact_ref: str
    artifact_sha256: str
    signature: str
    issued_at: datetime
    state: RolloutState
    created_by: Optional[str]
    halted_reason: Optional[str]


@dataclass(frozen=True)
class StageRecord:
    """
        Caller-facing stage read-model.
    """
    stage_id: str
    rollout_id: str
    stage_index: int
    rollout_policy: str
    policy_params: Mapping[str, Any]
    target_size: int
    state: StageState
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    success_count: int
    failure_count: int
    deferred_count: int


@dataclass(frozen=True)
class OfferRecord:
    """
        Caller-facing offer read-model.
    """
    offer_id: str
    stage_id: str
    client_id: str
    version: str
    offered_at: datetime
    outcome: OfferOutcome
    outcome_at: Optional[datetime]
    outcome_detail: Optional[Mapping[str, Any]]


def draft_rollout(
        *,
        db_session: DbSession,
        version: str,
        artifact_source: str,
        artifact_ref: str,
        signature: str = "",
        actor_id: Optional[str] = None
    ) -> RolloutRecord:
    """
        Persist a DRAFT rollout row. Resolves the artifact
        source via the registry to validate the
        ``artifact_ref`` and capture the canonical
        ``artifact_sha256``. Emits ``DRAFTED``.
    """
    if version is None or len(version) == 0:
        err_lines = ["draft_rollout requires a non-empty version."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    descriptor = _resolve_artifact_descriptor(
        artifact_source=artifact_source, artifact_ref=artifact_ref,
    )
    issued_at = utc_now()
    row = repository.insert_rollout(
        db_session=db_session,
        version=version,
        artifact_source=artifact_source,
        artifact_ref=artifact_ref,
        artifact_sha256=descriptor.artifact_sha256,
        signature=signature,
        issued_at=issued_at,
        created_by=actor_id,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UpgradeEventTopics.DRAFTED,
            payload={
                "rollout_id": str(row.rollout_id),
                "version": version,
                "artifact_source": artifact_source,
                "artifact_sha256": descriptor.artifact_sha256,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _rollout_to_record(row=row)
    return rtnval


def start_rollout(
        *,
        db_session: DbSession,
        rollout_id: str,
        rollout_policy: str,
        policy_params: Optional[Dict[str, Any]] = None,
        fleet: FleetSnapshot,
        actor_id: Optional[str] = None
    ) -> Tuple[RolloutRecord, StageRecord, List[OfferRecord]]:
    """
        Move a DRAFT rollout into ACTIVE, create stage 0,
        compute the offer set via the registered policy, and
        write one offer row per eligible client.

        :raises: RolloutNotFoundError when the rollout id
                 is unknown;
                 InvalidRolloutTransitionError when the
                 rollout is not currently DRAFT.
    """
    rollout_row = repository.find_rollout_by_id(
        db_session=db_session, rollout_id=rollout_id,
    )
    if rollout_row is None:
        err_lines = ["Rollout not found."]
        err_lines.append("ROLLOUT_ID: {}".format(rollout_id))
        err_msg = os.linesep.join(err_lines)
        raise RolloutNotFoundError(err_msg) from None
    if rollout_row.state != RolloutState.DRAFT:
        err_lines = ["Cannot start a rollout that is not DRAFT."]
        err_lines.append("ROLLOUT_ID: {}".format(rollout_id))
        err_lines.append("STATE: {}".format(rollout_row.state.value))
        err_msg = os.linesep.join(err_lines)
        raise InvalidRolloutTransitionError(err_msg) from None

    policy_cls = _resolve_policy(rollout_policy=rollout_policy)
    materialized_params = dict(policy_params or {})
    candidate_targets = policy_cls.compute_target_set(
        rollout_id=str(rollout_row.rollout_id),
        fleet=fleet,
        params=materialized_params,
    )

    pin_map = pins.get_pin_map(db_session=db_session)
    eligible: List[str] = []
    for client_id in candidate_targets:
        pinned_version = pin_map.get(client_id)
        if pinned_version is not None and pinned_version != rollout_row.version:
            continue
        if client_id in eligible:
            continue
        eligible.append(client_id)

    now = utc_now()
    stage_row = repository.insert_stage(
        db_session=db_session,
        rollout_id=str(rollout_row.rollout_id),
        stage_index=0,
        rollout_policy=rollout_policy,
        policy_params=materialized_params,
        target_size=len(eligible),
    )
    stage_row.state = StageState.ACTIVE
    stage_row.started_at = now
    db_session.flush()

    rollout_row.state = RolloutState.ACTIVE
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UpgradeEventTopics.STARTED,
            payload={
                "rollout_id": str(rollout_row.rollout_id),
                "version": rollout_row.version,
            },
            source_event_id=new_uuid(),
        ),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UpgradeEventTopics.STAGE_STARTED,
            payload={
                "rollout_id": str(rollout_row.rollout_id),
                "stage_id": str(stage_row.stage_id),
                "stage_index": 0,
                "target_size": len(eligible),
            },
            source_event_id=new_uuid(),
        ),
    )

    offers: List[OfferRecord] = []
    for client_id in eligible:
        offer_row = repository.insert_offer(
            db_session=db_session,
            stage_id=str(stage_row.stage_id),
            client_id=client_id,
            version=rollout_row.version,
            offered_at=now,
        )
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=UpgradeEventTopics.OFFERED,
                payload={
                    "offer_id": str(offer_row.offer_id),
                    "rollout_id": str(rollout_row.rollout_id),
                    "stage_id": str(stage_row.stage_id),
                    "client_id": client_id,
                    "version": rollout_row.version,
                },
                source_event_id=new_uuid(),
            ),
        )
        offers.append(_offer_to_record(row=offer_row))
    db_session.commit()
    rtnval = (
        _rollout_to_record(row=rollout_row),
        _stage_to_record(row=stage_row),
        offers,
    )
    return rtnval


def record_offer_outcome(
        *,
        db_session: DbSession,
        offer_id: str,
        outcome: OfferOutcome,
        detail: Optional[Mapping[str, Any]] = None
    ) -> OfferRecord:
    """
        Persist a terminal outcome for an outstanding offer
        and emit the matching outcome topic.
    """
    offer_row = repository.find_offer_by_id(
        db_session=db_session, offer_id=offer_id,
    )
    if offer_row is None:
        err_lines = ["Offer not found."]
        err_lines.append("OFFER_ID: {}".format(offer_id))
        err_msg = os.linesep.join(err_lines)
        raise RolloutNotFoundError(err_msg) from None
    now = utc_now()
    offer_row.outcome = outcome
    offer_row.outcome_at = now
    offer_row.outcome_detail = (
        dict(detail) if detail is not None else None
    )
    stage_row = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.stage_id == offer_row.stage_id)
        .first()
    )
    if stage_row is not None:
        if outcome == OfferOutcome.SUCCEEDED:
            stage_row.success_count = stage_row.success_count + 1
        elif outcome in (
            OfferOutcome.FAILED,
            OfferOutcome.SHA256_MISMATCH,
            OfferOutcome.FETCH_FAILED,
        ):
            stage_row.failure_count = stage_row.failure_count + 1
        elif outcome == OfferOutcome.DEFERRED:
            stage_row.deferred_count = stage_row.deferred_count + 1
        db_session.flush()

    topic = _topic_for_outcome(outcome=outcome)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=topic,
            payload={
                "offer_id": str(offer_row.offer_id),
                "stage_id": str(offer_row.stage_id),
                "client_id": offer_row.client_id,
                "version": offer_row.version,
                "outcome": outcome.value,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _offer_to_record(row=offer_row)
    return rtnval


def get_rollout(
        *,
        db_session: DbSession,
        rollout_id: str
    ) -> RolloutRecord:
    """
        Read by id.

        :raises: RolloutNotFoundError on miss.
    """
    row = repository.find_rollout_by_id(
        db_session=db_session, rollout_id=rollout_id,
    )
    if row is None:
        err_lines = ["Rollout not found."]
        err_lines.append("ROLLOUT_ID: {}".format(rollout_id))
        err_msg = os.linesep.join(err_lines)
        raise RolloutNotFoundError(err_msg) from None
    rtnval = _rollout_to_record(row=row)
    return rtnval


def list_rollouts(
        *,
        db_session: DbSession,
        state: Optional[RolloutState] = None
    ) -> List[RolloutRecord]:
    """
        List rollouts newest-first; optional state filter.
    """
    rows = repository.list_rollouts(
        db_session=db_session, state=state,
    )
    rtnval = [_rollout_to_record(row=r) for r in rows]
    return rtnval


def _resolve_artifact_descriptor(
        *, artifact_source: str, artifact_ref: str
    ) -> ArtifactDescriptor:
    candidates = list_factory_implementations(
        factory_protocol_name=UpgradeArtifactSourceProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            name = impl.source_name()
        except NotImplementedError:
            continue
        if name == artifact_source:
            descriptor = impl.describe(artifact_ref=artifact_ref)
            return descriptor
    err_lines = ["No registered upgrade_artifact_source for the supplied name."]
    err_lines.append("ARTIFACT_SOURCE: {!r}".format(artifact_source))
    err_msg = os.linesep.join(err_lines)
    raise ValueError(err_msg) from None


def _resolve_policy(*, rollout_policy: str):
    candidates = list_factory_implementations(
        factory_protocol_name=RolloutPolicyProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            name = impl.policy_name()
        except NotImplementedError:
            continue
        if name == rollout_policy:
            return impl
    err_lines = ["No registered rollout_policy for the supplied name."]
    err_lines.append("ROLLOUT_POLICY: {!r}".format(rollout_policy))
    err_msg = os.linesep.join(err_lines)
    raise ValueError(err_msg) from None


def _topic_for_outcome(*, outcome: OfferOutcome) -> str:
    if outcome == OfferOutcome.SUCCEEDED:
        return UpgradeEventTopics.SUCCEEDED
    if outcome in (OfferOutcome.FAILED, OfferOutcome.FETCH_FAILED):
        return UpgradeEventTopics.FAILED
    if outcome == OfferOutcome.SHA256_MISMATCH:
        return UpgradeEventTopics.INTEGRITY_FAILED
    if outcome == OfferOutcome.DEFERRED:
        return UpgradeEventTopics.DEFERRED
    if outcome == OfferOutcome.EXPIRED:
        return UpgradeEventTopics.FAILED
    return UpgradeEventTopics.OFFERED


def _rollout_to_record(*, row: AgentRollout) -> RolloutRecord:
    rtnval = RolloutRecord(
        rollout_id=str(row.rollout_id),
        version=row.version,
        artifact_source=row.artifact_source,
        artifact_ref=row.artifact_ref,
        artifact_sha256=row.artifact_sha256,
        signature=row.signature,
        issued_at=row.issued_at,
        state=row.state,
        created_by=(
            str(row.created_by) if row.created_by is not None else None
        ),
        halted_reason=row.halted_reason,
    )
    return rtnval


def _stage_to_record(*, row: AgentRolloutStage) -> StageRecord:
    rtnval = StageRecord(
        stage_id=str(row.stage_id),
        rollout_id=str(row.rollout_id),
        stage_index=row.stage_index,
        rollout_policy=row.rollout_policy,
        policy_params=dict(row.policy_params or {}),
        target_size=row.target_size,
        state=row.state,
        started_at=row.started_at,
        ended_at=row.ended_at,
        success_count=row.success_count,
        failure_count=row.failure_count,
        deferred_count=row.deferred_count,
    )
    return rtnval


def _offer_to_record(*, row: AgentUpgradeOffer) -> OfferRecord:
    rtnval = OfferRecord(
        offer_id=str(row.offer_id),
        stage_id=str(row.stage_id),
        client_id=row.client_id,
        version=row.version,
        offered_at=row.offered_at,
        outcome=row.outcome,
        outcome_at=row.outcome_at,
        outcome_detail=(
            dict(row.outcome_detail) if row.outcome_detail is not None else None
        ),
    )
    return rtnval
