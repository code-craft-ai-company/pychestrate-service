"""
.. module:: audit.sink_health
    :synopsis: Canonical-sink health probe + bus emit.

The canonical-sink probe runs out-of-band (M3 wires it onto a
periodic scheduler). When a sink transitions from healthy to
unhealthy or vice versa, the helper enqueues
``entity.audit.sink.unhealthy`` / ``entity.audit.sink.healthy``
through the outbox so downstream subscribers can flip the
write-blocked flag on the request path.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.audit.events import AuditEventTopics
from automojo.pychestrate.webservice.audit.factories.audit_sink import (
    AuditSinkProtocol,
    SinkHealth,
)
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


_LOCK = threading.RLock()
_LAST_SEEN: Dict[str, bool] = {}


@dataclass(frozen=True)
class SinkHealthSnapshot:
    """
        Snapshot of a single sink's health.
    """
    sink_name: str
    is_canonical: bool
    healthy: bool
    reason: str


def reset_for_testing() -> None:
    """
        Drop the last-seen cache so test cases do not leak
        prior transitions.
    """
    with _LOCK:
        _LAST_SEEN.clear()
    return


def evaluate_sink_health(
        *,
        db_session: DbSession
    ) -> List[SinkHealthSnapshot]:
    """
        Walk every registered sink, run its health probe, emit
        a transition topic when the verdict changed since the
        last probe, and return the per-sink snapshots.
    """
    sinks = _list_sinks()
    snapshots: List[SinkHealthSnapshot] = []
    transitions: List[SinkHealthSnapshot] = []
    for sink_cls in sinks:
        try:
            health = sink_cls.health_check()
        except NotImplementedError:
            continue
        is_canonical = bool(sink_cls.is_canonical())
        snapshot = SinkHealthSnapshot(
            sink_name=sink_cls.sink_name(),
            is_canonical=is_canonical,
            healthy=bool(health.healthy),
            reason=health.reason or "",
        )
        snapshots.append(snapshot)
        with _LOCK:
            prior = _LAST_SEEN.get(snapshot.sink_name)
            _LAST_SEEN[snapshot.sink_name] = snapshot.healthy
        if prior is None:
            # First observation — emit only if the sink is
            # currently unhealthy so operators see the gap.
            if snapshot.healthy is False:
                transitions.append(snapshot)
            continue
        if prior != snapshot.healthy:
            transitions.append(snapshot)

    for snapshot in transitions:
        topic = (
            AuditEventTopics.AUDIT_SINK_HEALTHY
            if snapshot.healthy is True
            else AuditEventTopics.AUDIT_SINK_UNHEALTHY
        )
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=topic,
                payload={
                    "sink_name": snapshot.sink_name,
                    "is_canonical": snapshot.is_canonical,
                    "reason": snapshot.reason,
                    "evaluated_at": utc_now().isoformat(),
                },
                source_event_id=new_uuid(),
            ),
        )
    if len(transitions) > 0:
        db_session.commit()
    return snapshots


def _list_sinks() -> List[Type[AuditSinkProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=AuditSinkProtocol.factory_protocol_name,
    )
    rtnval: List[Type[AuditSinkProtocol]] = list(candidates)
    return rtnval
