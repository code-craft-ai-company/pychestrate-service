"""
.. module:: clients.upgrades.pins
    :synopsis: Pod-scoped pin management.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.clients.upgrades import repository
from ccai.pychestrate.webservice.clients.upgrades.events import (
    UpgradeEventTopics,
)
from ccai.pychestrate.webservice.clients.upgrades.models import AgentPodPin
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


@dataclass(frozen=True)
class PodPinView:
    """
        Caller-facing pin read-model.
    """
    pod_id: str
    pinned_version: str
    set_by: Optional[str]
    set_at: datetime
    reason: Optional[str]


def set_pod_pin(
        *,
        db_session: DbSession,
        pod_id: str,
        version: str,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> PodPinView:
    """
        Pin ``pod_id`` to ``version``. Idempotent: re-pinning
        the same pod overwrites the prior version. Emits
        ``PIN_SET``.

        :raises: ValueError on empty pod_id / version.
    """
    if pod_id is None or len(pod_id) == 0:
        err_lines = ["set_pod_pin requires a non-empty pod_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if version is None or len(version) == 0:
        err_lines = ["set_pod_pin requires a non-empty version."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    now = utc_now()
    row = repository.upsert_pod_pin(
        db_session=db_session,
        pod_id=pod_id,
        pinned_version=version,
        set_by=actor_id,
        set_at=now,
        reason=reason,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UpgradeEventTopics.PIN_SET,
            payload={
                "pod_id": pod_id,
                "pinned_version": version,
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def delete_pod_pin(
        *,
        db_session: DbSession,
        pod_id: str,
        actor_id: Optional[str] = None
    ) -> bool:
    """
        Remove a pin. Returns ``True`` when a row was deleted,
        ``False`` when no pin existed (idempotent). Emits
        ``PIN_CLEARED`` only on the first transition.
    """
    deleted = repository.delete_pod_pin_row(
        db_session=db_session, pod_id=pod_id,
    )
    if deleted is True:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=UpgradeEventTopics.PIN_CLEARED,
                payload={"pod_id": pod_id, "actor_id": actor_id},
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
    return deleted


def get_pin_map(*, db_session: DbSession) -> Dict[str, str]:
    """
        Return ``{pod_id: pinned_version}`` for every active
        pin. Used by the orchestrator to filter offer sets.
    """
    rows = repository.list_pod_pins(db_session=db_session)
    rtnval: Dict[str, str] = {}
    for row in rows:
        rtnval[row.pod_id] = row.pinned_version
    return rtnval


def _row_to_view(*, row: AgentPodPin) -> PodPinView:
    rtnval = PodPinView(
        pod_id=row.pod_id,
        pinned_version=row.pinned_version,
        set_by=str(row.set_by) if row.set_by is not None else None,
        set_at=row.set_at,
        reason=row.reason,
    )
    return rtnval
