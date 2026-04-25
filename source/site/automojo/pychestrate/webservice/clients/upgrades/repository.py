"""
.. module:: clients.upgrades.repository
    :synopsis: CRUD helpers for agent-rollout / pin rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.clients.upgrades.enums import (
    OfferOutcome,
    RolloutState,
    StageState,
)
from automojo.pychestrate.webservice.clients.upgrades.models import (
    AgentPodPin,
    AgentRollout,
    AgentRolloutStage,
    AgentUpgradeOffer,
)


def insert_rollout(
        *,
        db_session: DbSession,
        version: str,
        artifact_source: str,
        artifact_ref: str,
        artifact_sha256: str,
        signature: str,
        issued_at: datetime,
        created_by: Optional[str]
    ) -> AgentRollout:
    row = AgentRollout(
        rollout_id=new_uuid(),
        version=version,
        artifact_source=artifact_source,
        artifact_ref=artifact_ref,
        artifact_sha256=artifact_sha256,
        signature=signature,
        issued_at=issued_at,
        state=RolloutState.DRAFT,
        created_by=created_by,
        halted_reason=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_rollout_by_id(
        *,
        db_session: DbSession,
        rollout_id: str
    ) -> Optional[AgentRollout]:
    rtnval = (
        db_session.query(AgentRollout)
        .filter(AgentRollout.rollout_id == rollout_id)
        .first()
    )
    return rtnval


def list_rollouts(
        *,
        db_session: DbSession,
        state: Optional[RolloutState] = None
    ) -> List[AgentRollout]:
    query = db_session.query(AgentRollout)
    if state is not None:
        query = query.filter(AgentRollout.state == state)
    rows = query.order_by(AgentRollout.issued_at.desc()).all()
    rtnval = list(rows)
    return rtnval


def insert_stage(
        *,
        db_session: DbSession,
        rollout_id: str,
        stage_index: int,
        rollout_policy: str,
        policy_params: Dict[str, Any],
        target_size: int
    ) -> AgentRolloutStage:
    row = AgentRolloutStage(
        stage_id=new_uuid(),
        rollout_id=rollout_id,
        stage_index=stage_index,
        rollout_policy=rollout_policy,
        policy_params=dict(policy_params or {}),
        target_size=target_size,
        state=StageState.PENDING,
        started_at=None,
        ended_at=None,
        success_count=0,
        failure_count=0,
        deferred_count=0,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_stages_for_rollout(
        *,
        db_session: DbSession,
        rollout_id: str
    ) -> List[AgentRolloutStage]:
    rows = (
        db_session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.rollout_id == rollout_id)
        .order_by(AgentRolloutStage.stage_index.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_offer(
        *,
        db_session: DbSession,
        stage_id: str,
        client_id: str,
        version: str,
        offered_at: datetime
    ) -> AgentUpgradeOffer:
    row = AgentUpgradeOffer(
        offer_id=new_uuid(),
        stage_id=stage_id,
        client_id=client_id,
        version=version,
        offered_at=offered_at,
        outcome=OfferOutcome.OFFERED,
        outcome_at=None,
        outcome_detail=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_offers_for_stage(
        *,
        db_session: DbSession,
        stage_id: str
    ) -> List[AgentUpgradeOffer]:
    rows = (
        db_session.query(AgentUpgradeOffer)
        .filter(AgentUpgradeOffer.stage_id == stage_id)
        .order_by(AgentUpgradeOffer.offered_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_offer_by_id(
        *,
        db_session: DbSession,
        offer_id: str
    ) -> Optional[AgentUpgradeOffer]:
    rtnval = (
        db_session.query(AgentUpgradeOffer)
        .filter(AgentUpgradeOffer.offer_id == offer_id)
        .first()
    )
    return rtnval


def upsert_pod_pin(
        *,
        db_session: DbSession,
        pod_id: str,
        pinned_version: str,
        set_by: Optional[str],
        set_at: datetime,
        reason: Optional[str]
    ) -> AgentPodPin:
    row = (
        db_session.query(AgentPodPin)
        .filter(AgentPodPin.pod_id == pod_id)
        .first()
    )
    if row is None:
        row = AgentPodPin(
            pod_id=pod_id,
            pinned_version=pinned_version,
            set_by=set_by,
            set_at=set_at,
            reason=reason,
        )
        db_session.add(row)
    else:
        row.pinned_version = pinned_version
        row.set_by = set_by
        row.set_at = set_at
        row.reason = reason
    db_session.flush()
    return row


def find_pod_pin(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> Optional[AgentPodPin]:
    rtnval = (
        db_session.query(AgentPodPin)
        .filter(AgentPodPin.pod_id == pod_id)
        .first()
    )
    return rtnval


def list_pod_pins(*, db_session: DbSession) -> List[AgentPodPin]:
    rows = db_session.query(AgentPodPin).all()
    rtnval = list(rows)
    return rtnval


def delete_pod_pin_row(*, db_session: DbSession, pod_id: str) -> bool:
    row = find_pod_pin(db_session=db_session, pod_id=pod_id)
    if row is None:
        return False
    db_session.delete(row)
    db_session.flush()
    return True
