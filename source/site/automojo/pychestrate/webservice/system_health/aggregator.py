"""
.. module:: system_health.aggregator
    :synopsis: Snapshot-driven overall-status / per-probe transition emits.

The aggregator compares the latest :class:`HealthSnapshot`
against the prior observation. When the overall verdict
flips (or a per-probe ok↔fail transition fires) it emits the
matching topic onto the in-process event bus. The aggregator
holds no DB session — the topics fire on the bus directly so
operators can consume them without enlisting in a request
transaction.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from datetime import datetime, timezone
from typing import Dict, Optional

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
)
from automojo.pychestrate.webservice.system_health.events import (
    SystemHealthEventTopics,
)
from automojo.pychestrate.webservice.system_health.registry import (
    HealthRegistry,
    HealthSnapshot,
    OverallStatus,
    ProbeResult,
    ProbeStatus,
)


_LOCK = threading.RLock()
_LAST_OVERALL: Optional[OverallStatus] = None
_LAST_PROBE_STATUS: Dict[str, ProbeStatus] = {}


def reset_for_testing() -> None:
    """
        Drop the aggregator's last-seen cache.
    """
    global _LAST_OVERALL
    with _LOCK:
        _LAST_OVERALL = None
        _LAST_PROBE_STATUS.clear()
    return


def evaluate_transitions(*, registry: HealthRegistry) -> HealthSnapshot:
    """
        Take a fresh snapshot, emit transition topics for any
        per-probe or overall changes since the last call, and
        return the snapshot.
    """
    snapshot = registry.snapshot()
    _maybe_emit_overall(snapshot=snapshot)
    _maybe_emit_per_probe(snapshot=snapshot)
    return snapshot


def _maybe_emit_overall(*, snapshot: HealthSnapshot) -> None:
    global _LAST_OVERALL
    with _LOCK:
        prior = _LAST_OVERALL
        _LAST_OVERALL = snapshot.overall
    if prior is None:
        # Suppress the first observation so the aggregator does
        # not announce an overall change for the bootstrap
        # transition from "no probes" to "first verdict".
        return
    if prior == snapshot.overall:
        return
    publish(
        event=EntityEvent(
            topic=SystemHealthEventTopics.OVERALL_CHANGED,
            payload={
                "from": prior.value,
                "to": snapshot.overall.value,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
                "failing_readiness_probes": list(
                    snapshot.failing_readiness_probes,
                ),
            },
            source_event_id=new_uuid(),
        ),
    )
    return


def _maybe_emit_per_probe(*, snapshot: HealthSnapshot) -> None:
    transitions = []
    with _LOCK:
        for name, _kind, result in snapshot.probes:
            current = (
                result.status if result is not None else ProbeStatus.UNKNOWN
            )
            prior = _LAST_PROBE_STATUS.get(name)
            _LAST_PROBE_STATUS[name] = current
            if prior is None:
                continue
            if prior == current:
                continue
            transitions.append((name, prior, current, result))
    for name, prior, current, result in transitions:
        if current == ProbeStatus.FAIL and prior != ProbeStatus.FAIL:
            topic = SystemHealthEventTopics.PROBE_FAILED
        elif prior == ProbeStatus.FAIL and current == ProbeStatus.OK:
            topic = SystemHealthEventTopics.PROBE_RECOVERED
        else:
            continue
        publish(
            event=EntityEvent(
                topic=topic,
                payload={
                    "name": name,
                    "from": prior.value,
                    "to": current.value,
                    "last_error": (
                        result.last_error if result is not None else None
                    ),
                    "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
                },
                source_event_id=new_uuid(),
            ),
        )
    return
