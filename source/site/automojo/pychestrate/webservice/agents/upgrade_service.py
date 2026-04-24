"""
.. module:: agents.upgrade_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-agent-upgrade-channel service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Optional, Sequence

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.agents.events import AgentUpgradeEventTopics
from automojo.pychestrate.webservice.agents.exceptions import (
    RolloutNotFoundError,
    RolloutStateTransitionError,
)
from automojo.pychestrate.webservice.agents.factories.artifact_source import (
    UpgradeArtifactSourceProtocol,
)
from automojo.pychestrate.webservice.agents.factories.rollout_policy import (
    RolloutPolicyProtocol,
)
from automojo.pychestrate.webservice.agents.models import (
    AgentPodPin,
    AgentRollout,
    AgentRolloutStage,
    AgentUpgradeOffer,
    RolloutStageState,
    RolloutState,
    UpgradeOfferOutcome,
)
from automojo.pychestrate.webservice.extensions.registry import list_factory_implementations
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


def draft_rollout(
        *,
        db_session: DbSession,
        version: str,
        artifact_source: str,
        artifact_ref: str,
        signature: Optional[bytes],
        actor_user_id: Optional[str]
    ) -> AgentRollout:
    """
        Create a rollout in DRAFT state.
    """
    if version is None or len(version.strip()) == 0:
        raise SemanticError("rollout version is required")

    rollout = AgentRollout(
        rollout_id=new_uuid(),
        version=version.strip(),
        artifact_source=artifact_source.strip() if artifact_source is not None else "",
        artifact_ref=artifact_ref.strip() if artifact_ref is not None else "",
        signature=signature,
        state=RolloutState.DRAFT,
        created_at=utc_now(),
        created_by=actor_user_id,
    )
    db_session.add(rollout)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AgentUpgradeEventTopics.ROLLOUT_DRAFTED,
            payload={
                "rollout_id": str(rollout.rollout_id),
                "version": rollout.version,
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return rollout


def start_rollout(
        *,
        db_session: DbSession,
        rollout_id: str,
        candidate_client_ids: Sequence[str],
        target_size: int,
        actor_user_id: Optional[str]
    ) -> List[AgentUpgradeOffer]:
    """
        Transition a DRAFT rollout to ACTIVE, resolve the artifact via the
        registered ``upgrade_artifact_source`` factory, pick targets via
        the registered ``rollout_policy``, and emit an
        :class:`AgentUpgradeOffer` per picked client.

        :raises: RolloutNotFoundError, RolloutStateTransitionError
    """
    rollout = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == rollout_id)
        .first()
    )
    if rollout is None:
        err_msg_lines = ["Rollout not found."]
        err_msg_lines.append("ROLLOUT_ID: {}".format(rollout_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise RolloutNotFoundError(err_msg) from None
    if rollout.state != RolloutState.DRAFT:
        err_msg_lines = ["Rollout must be DRAFT to start."]
        err_msg_lines.append("ROLLOUT_ID: {}".format(rollout_id))
        err_msg_lines.append("CURRENT_STATE: {}".format(rollout.state.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise RolloutStateTransitionError(err_msg) from None

    artifact_handle = _resolve_artifact_handle(
        artifact_source=rollout.artifact_source,
        artifact_ref=rollout.artifact_ref,
    )

    policy = _first_registered_rollout_policy()
    if policy is None:
        raise RolloutStateTransitionError("No rollout_policy implementation is registered")

    picked = list(policy.pick_targets(
        candidate_client_ids=candidate_client_ids,
        target_size=int(target_size),
    ))

    rollout.state = RolloutState.ACTIVE
    db_session.add(rollout)
    db_session.flush()

    offers: List[AgentUpgradeOffer] = []
    now = utc_now()
    for client_id in picked:
        offer = AgentUpgradeOffer(
            offer_id=new_uuid(),
            rollout_id=rollout.rollout_id,
            client_id=client_id,
            version=rollout.version,
            outcome=UpgradeOfferOutcome.OFFERED,
            offered_at=now,
            resolved_at=None,
            detail=None,
        )
        db_session.add(offer)
        offers.append(offer)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AgentUpgradeEventTopics.ROLLOUT_STARTED,
            payload={
                "rollout_id": str(rollout.rollout_id),
                "version": rollout.version,
                "artifact_sha256": artifact_handle.sha256,
                "offer_count": len(offers),
            },
            source_event_id=new_uuid(),
        ),
    )
    for offer in offers:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=AgentUpgradeEventTopics.UPGRADE_OFFERED,
                payload={
                    "offer_id": str(offer.offer_id),
                    "rollout_id": str(rollout.rollout_id),
                    "client_id": str(offer.client_id),
                    "version": rollout.version,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    return offers


def add_rollout_stage(
        *,
        db_session: DbSession,
        rollout_id: str,
        rollout_policy: str,
        target_size: int
    ) -> AgentRolloutStage:
    """
        Append a new stage to a rollout (M2). Stages land in PENDING.
    """
    rollout = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == rollout_id)
        .first()
    )
    if rollout is None:
        raise RolloutNotFoundError("Rollout {} not found".format(rollout_id))

    existing_count = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.rollout_id == rollout_id)
        .count()
    )
    stage = AgentRolloutStage(
        stage_id=new_uuid(),
        rollout_id=rollout.rollout_id,
        stage_index=int(existing_count),
        rollout_policy=rollout_policy,
        target_size=int(target_size),
        state=RolloutStageState.PENDING,
        created_at=utc_now(),
    )
    db_session.add(stage)
    db_session.flush()
    db_session.commit()
    return stage


def start_rollout_stage(
        *,
        db_session: DbSession,
        stage_id: str,
        candidate_client_ids: Sequence[str]
    ) -> List[AgentUpgradeOffer]:
    """
        Pick targets for a PENDING stage and emit offers, honoring pins.
    """
    stage = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.stage_id == stage_id)
        .first()
    )
    if stage is None:
        raise RolloutNotFoundError("Stage {} not found".format(stage_id))
    if stage.state != RolloutStageState.PENDING:
        raise RolloutStateTransitionError(
            "Stage must be PENDING (current: {})".format(stage.state.value),
        )

    rollout = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == stage.rollout_id)
        .first()
    )
    if rollout is None:
        raise RolloutNotFoundError("Parent rollout missing")

    pins = {
        str(p.pod_id): p.pinned_version
        for p in db_session.query(AgentPodPin).all()
    }

    policy = _first_registered_rollout_policy()
    if policy is None:
        raise RolloutStateTransitionError("No rollout_policy implementation is registered")

    picked = list(policy.pick_targets(
        candidate_client_ids=candidate_client_ids,
        target_size=int(stage.target_size),
    ))

    stage.state = RolloutStageState.ACTIVE
    stage.started_at = utc_now()
    db_session.add(stage)
    db_session.flush()

    offers: List[AgentUpgradeOffer] = []
    for client_id in picked:
        if client_id in pins and pins[client_id] != rollout.version:
            stage.deferred_count = int(stage.deferred_count or 0) + 1
            continue
        offer = AgentUpgradeOffer(
            offer_id=new_uuid(),
            rollout_id=rollout.rollout_id,
            client_id=client_id,
            version=rollout.version,
            outcome=UpgradeOfferOutcome.OFFERED,
            offered_at=utc_now(),
            resolved_at=None,
            detail=None,
        )
        db_session.add(offer)
        offers.append(offer)

    db_session.add(stage)
    db_session.flush()
    db_session.commit()
    return offers


def halt_rollout(
        *,
        db_session: DbSession,
        rollout_id: str,
        actor_user_id: Optional[str]
    ) -> AgentRollout:
    """
        Transition a rollout to HALTED; pending/active stages follow.
    """
    rollout = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == rollout_id)
        .first()
    )
    if rollout is None:
        raise RolloutNotFoundError("Rollout {} not found".format(rollout_id))
    if rollout.state in (RolloutState.COMPLETED, RolloutState.HALTED):
        return rollout

    rollout.state = RolloutState.HALTED
    db_session.add(rollout)
    stages = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.rollout_id == rollout_id)
        .filter(AgentRolloutStage.state.in_((RolloutStageState.PENDING, RolloutStageState.ACTIVE)))
        .all()
    )
    for stage in stages:
        stage.state = RolloutStageState.HALTED
        db_session.add(stage)
    db_session.flush()
    db_session.commit()
    return rollout


def resume_rollout(
        *,
        db_session: DbSession,
        rollout_id: str,
        actor_user_id: Optional[str]
    ) -> AgentRollout:
    """
        Transition HALTED → ACTIVE; halted stages → PENDING.
    """
    rollout = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == rollout_id)
        .first()
    )
    if rollout is None:
        raise RolloutNotFoundError("Rollout {} not found".format(rollout_id))
    if rollout.state != RolloutState.HALTED:
        raise RolloutStateTransitionError(
            "Rollout must be HALTED to resume (current: {})".format(rollout.state.value),
        )
    rollout.state = RolloutState.ACTIVE
    db_session.add(rollout)
    stages = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.rollout_id == rollout_id)
        .filter(AgentRolloutStage.state == RolloutStageState.HALTED)
        .all()
    )
    for stage in stages:
        stage.state = RolloutStageState.PENDING
        db_session.add(stage)
    db_session.flush()
    db_session.commit()
    return rollout


def pin_pod_version(
        *,
        db_session: DbSession,
        pod_id: str,
        version: str,
        reason: str
    ) -> AgentPodPin:
    """
        Create or refresh an :class:`AgentPodPin`.
    """
    existing = (
        db_session.query(AgentPodPin)
        .filter(AgentPodPin.pod_id == pod_id)
        .first()
    )
    now = utc_now()
    if existing is not None:
        existing.pinned_version = version
        existing.reason = reason if reason is not None else ""
        existing.set_at = now
        db_session.add(existing)
        db_session.flush()
        db_session.commit()
        return existing
    row = AgentPodPin(
        pod_id=pod_id,
        pinned_version=version,
        reason=reason if reason is not None else "",
        set_at=now,
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return row


def record_upgrade_outcome(
        *,
        db_session: DbSession,
        offer_id: str,
        outcome: UpgradeOfferOutcome,
        detail: Optional[str]
    ) -> AgentUpgradeOffer:
    """
        Finalize an offer.
    """
    offer = (
        db_session.query(AgentUpgradeOffer)
        .filter(AgentUpgradeOffer.offer_id == offer_id)
        .first()
    )
    if offer is None:
        err_msg_lines = ["Upgrade offer not found."]
        err_msg_lines.append("OFFER_ID: {}".format(offer_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise RolloutNotFoundError(err_msg) from None

    offer.outcome = outcome
    offer.resolved_at = utc_now()
    offer.detail = detail
    db_session.add(offer)
    db_session.flush()

    if outcome == UpgradeOfferOutcome.SUCCEEDED:
        topic = AgentUpgradeEventTopics.UPGRADE_SUCCEEDED
    else:
        topic = AgentUpgradeEventTopics.UPGRADE_FAILED
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=topic,
            payload={
                "offer_id": str(offer.offer_id),
                "rollout_id": str(offer.rollout_id),
                "client_id": str(offer.client_id),
                "outcome": outcome.value,
                "detail": detail,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return offer


def _resolve_artifact_handle(*, artifact_source: str, artifact_ref: str):
    """
        Walk the registered ``upgrade_artifact_source`` factories and
        return the first :class:`ArtifactHandle` that accepts the ref.
    """
    impls = list_factory_implementations(factory_protocol_name="upgrade_artifact_source")
    for impl in impls:
        declared = getattr(impl, "source_name", "")
        if declared == artifact_source or artifact_source == "":
            rtnval = impl.resolve(artifact_ref=artifact_ref)
            return rtnval
    err_msg_lines = ["No upgrade_artifact_source implementation accepted the source."]
    err_msg_lines.append("ARTIFACT_SOURCE: {}".format(artifact_source))
    err_msg = os.linesep.join(err_msg_lines)
    raise RolloutStateTransitionError(err_msg) from None


def _first_registered_rollout_policy() -> Optional[RolloutPolicyProtocol]:
    """
        Return the highest-priority rollout policy or None.
    """
    impls = list_factory_implementations(factory_protocol_name="rollout_policy")
    if len(impls) == 0:
        return None
    rtnval = impls[0]
    return rtnval
