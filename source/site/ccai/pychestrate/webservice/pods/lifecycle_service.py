"""
.. module:: pods.lifecycle_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-pod-lifecycle state machine + service surface.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.pods.events import PodLifecycleEventTopics
from ccai.pychestrate.webservice.pods.exceptions import (
    PodDefinitionNotFoundError,
    PodStateTransitionError,
)
from ccai.pychestrate.webservice.pods.models import (
    PodLifecycleLog,
    PodRuntimeState,
    PodState,
)


class LifecycleEventKind:
    """
        Canonical pod lifecycle event kinds.
    """
    DEFINED: str = "defined"
    PROVISION_STARTED: str = "provision_started"
    PROVISION_COMPLETED: str = "provision_completed"
    PROVISION_FAILED: str = "provision_failed"
    REGISTERED: str = "registered"
    ACQUIRE: str = "acquire"
    RELEASE: str = "release"
    DRAIN: str = "drain"
    DEREGISTER: str = "deregister"
    CLIENT_LOST: str = "client_lost"
    CLIENT_RECOVERED: str = "client_recovered"


TRANSITIONS: Mapping[Tuple[PodState, str], PodState] = {
    (PodState.DEFINED, LifecycleEventKind.PROVISION_STARTED): PodState.PROVISIONING,
    (PodState.PROVISIONING, LifecycleEventKind.PROVISION_COMPLETED): PodState.READY,
    (PodState.PROVISIONING, LifecycleEventKind.PROVISION_FAILED): PodState.FAILED,
    (PodState.DEFINED, LifecycleEventKind.REGISTERED): PodState.READY,
    (PodState.READY, LifecycleEventKind.ACQUIRE): PodState.IN_USE,
    (PodState.IN_USE, LifecycleEventKind.RELEASE): PodState.READY,
    (PodState.READY, LifecycleEventKind.DRAIN): PodState.DRAINING,
    (PodState.IN_USE, LifecycleEventKind.DRAIN): PodState.DRAINING,
    (PodState.DRAINING, LifecycleEventKind.DEREGISTER): PodState.RELEASED,
    (PodState.READY, LifecycleEventKind.CLIENT_LOST): PodState.CLIENT_LOST,
    (PodState.IN_USE, LifecycleEventKind.CLIENT_LOST): PodState.CLIENT_LOST,
    (PodState.CLIENT_LOST, LifecycleEventKind.CLIENT_RECOVERED): PodState.READY,
    (PodState.FAILED, LifecycleEventKind.DEREGISTER): PodState.RELEASED,
}


def transition_from(*, current: PodState, event_kind: str) -> PodState:
    """
        Return the target state for ``(current, event_kind)`` or raise.

        :raises: PodStateTransitionError
    """
    target = TRANSITIONS.get((current, event_kind), None)
    if target is None:
        err_msg_lines = ["Pod lifecycle transition is not permitted."]
        err_msg_lines.append("CURRENT: {}".format(current.value))
        err_msg_lines.append("EVENT: {}".format(event_kind))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodStateTransitionError(err_msg) from None
    return target


def initialize_pod_state(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> PodRuntimeState:
    """
        Insert a :class:`PodRuntimeState` row in ``DEFINED`` for a new pod.
    """
    existing = db_session.query(PodRuntimeState).filter(
        PodRuntimeState.pod_id == pod_id,
    ).first()
    if existing is not None:
        return existing

    row = PodRuntimeState(
        pod_id=pod_id,
        state=PodState.DEFINED,
        previous_state=None,
        last_transition_at=utc_now(),
        last_transition_event=LifecycleEventKind.DEFINED,
        in_use_since=None,
        runs_remaining=None,
        transition_cursor=0,
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return row


def apply_transition(
        *,
        db_session: DbSession,
        pod_id: str,
        event_kind: str,
        event_payload: Optional[Mapping[str, Any]],
        actor: Optional[str]
    ) -> PodRuntimeState:
    """
        Look up the pod's current state, validate the transition, update
        the row, append a :class:`PodLifecycleLog` entry, and publish
        ``entity.pod.state_changed``.

        :raises: PodDefinitionNotFoundError, PodStateTransitionError
    """
    state_row = (
        db_session.query(PodRuntimeState)
        .filter(PodRuntimeState.pod_id == pod_id)
        .first()
    )
    if state_row is None:
        err_msg_lines = ["Pod runtime state not initialized."]
        err_msg_lines.append("POD_ID: {}".format(pod_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodDefinitionNotFoundError(err_msg) from None

    target = transition_from(current=state_row.state, event_kind=event_kind)
    from_state = state_row.state
    now = utc_now()

    state_row.previous_state = from_state
    state_row.state = target
    state_row.last_transition_at = now
    state_row.last_transition_event = event_kind
    state_row.transition_cursor = int(state_row.transition_cursor or 0) + 1
    if target == PodState.IN_USE:
        state_row.in_use_since = now
    else:
        if from_state == PodState.IN_USE:
            state_row.in_use_since = None

    db_session.add(state_row)

    log_row = PodLifecycleLog(
        log_id=new_uuid(),
        pod_id=pod_id,
        from_state=from_state,
        to_state=target,
        event_kind=event_kind,
        event_payload=dict(event_payload) if event_payload is not None else {},
        actor=actor,
        applied_at=now,
    )
    db_session.add(log_row)
    db_session.flush()

    event_body = {
        "pod_id": str(pod_id),
        "from_state": from_state.value,
        "to_state": target.value,
        "event_kind": event_kind,
        "actor": actor,
        "applied_at": now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodLifecycleEventTopics.POD_STATE_CHANGED,
            payload=event_body,
            source_event_id=new_uuid(),
        ),
    )

    db_session.commit()
    return state_row


def read_state(*, db_session: DbSession, pod_id: str) -> PodRuntimeState:
    """
        Return the :class:`PodRuntimeState` for a pod, or raise.
    """
    row = (
        db_session.query(PodRuntimeState)
        .filter(PodRuntimeState.pod_id == pod_id)
        .first()
    )
    if row is None:
        err_msg_lines = ["Pod runtime state not initialized."]
        err_msg_lines.append("POD_ID: {}".format(pod_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodDefinitionNotFoundError(err_msg) from None
    rtnval = row
    return rtnval


def read_state_history(
        *,
        db_session: DbSession,
        pod_id: str,
        offset: int,
        limit: int
    ) -> List[PodLifecycleLog]:
    """
        Return the paginated transition log for a pod, newest first.
    """
    query = db_session.query(PodLifecycleLog).filter(PodLifecycleLog.pod_id == pod_id)
    query = query.order_by(PodLifecycleLog.applied_at.desc())
    rtnval = query.offset(offset).limit(limit).all()
    return rtnval
