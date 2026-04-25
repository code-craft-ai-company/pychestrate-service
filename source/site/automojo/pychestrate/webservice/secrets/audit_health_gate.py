"""
.. module:: secrets.audit_health_gate
    :synopsis: Audit-sink health gate for the secrets vault.

The gate listens for ``entity.audit.sink.unhealthy`` /
``entity.audit.sink.healthy`` emits from the audit feature
and flips a process-local ``write_blocked`` flag. Mutating
secrets entry points (put_secret / rotate_secret /
force_expire_secret) consult :func:`is_write_blocked` and
raise :class:`AuditUnavailableError` until the canonical sink
recovers — the NFR-4 fail-closed invariant.

Only the canonical sink trips the gate. A non-canonical
fan-out sink reporting unhealthy is recorded but does not
block writes (callers can keep landing audit rows on the
canonical sink + retry the fan-out later).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from datetime import datetime, timezone
from typing import Optional, Set

from automojo.pychestrate.webservice.audit.events import AuditEventTopics
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)


_LOCK = threading.RLock()
_BLOCK_REASONS: Set[str] = set()
_LAST_TRANSITION_AT: Optional[datetime] = None
_INSTALLED: bool = False


def install_subscribers() -> None:
    """
        Subscribe the gate handlers to the audit-sink health
        topics. Idempotent — second installation is a no-op.

        Safe to call once at bootstrap.
    """
    global _INSTALLED
    with _LOCK:
        if _INSTALLED is True:
            return
        _INSTALLED = True
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        subscriber=_on_unhealthy,
    )
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_HEALTHY,
        subscriber=_on_healthy,
    )
    return


def is_write_blocked() -> bool:
    """
        Return ``True`` when at least one canonical sink is
        currently reporting unhealthy.
    """
    with _LOCK:
        rtnval = len(_BLOCK_REASONS) > 0
    return rtnval


def blocking_sinks() -> Set[str]:
    """
        Return the set of canonical sinks whose latest emit
        was unhealthy. Useful for the error message detail.
    """
    with _LOCK:
        rtnval = set(_BLOCK_REASONS)
    return rtnval


def reset_for_testing() -> None:
    """
        Drop the gate's internal state. Tests use this to keep
        prior subscriptions / block-state from leaking.
    """
    global _INSTALLED, _LAST_TRANSITION_AT
    with _LOCK:
        _BLOCK_REASONS.clear()
        _LAST_TRANSITION_AT = None
        _INSTALLED = False
    return


def _on_unhealthy(event: EntityEvent) -> None:
    payload = event.payload or {}
    if payload.get("is_canonical") is not True:
        return
    sink_name = payload.get("sink_name")
    if sink_name is None:
        return
    global _LAST_TRANSITION_AT
    with _LOCK:
        _BLOCK_REASONS.add(sink_name)
        _LAST_TRANSITION_AT = datetime.now(tz=timezone.utc)
    return


def _on_healthy(event: EntityEvent) -> None:
    payload = event.payload or {}
    if payload.get("is_canonical") is not True:
        return
    sink_name = payload.get("sink_name")
    if sink_name is None:
        return
    global _LAST_TRANSITION_AT
    with _LOCK:
        _BLOCK_REASONS.discard(sink_name)
        _LAST_TRANSITION_AT = datetime.now(tz=timezone.utc)
    return
