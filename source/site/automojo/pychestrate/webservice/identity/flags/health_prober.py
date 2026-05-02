"""
.. module:: identity.flags.health_prober
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Health prober for registered feature_flag_backend implementations.

.. moduleauthor:: Automation Mojo LLC

The prober is invoked on a cadence (default 30 s) by the service
scheduler and per-test by the integration suite. It calls
``backend.health_check()`` on every registered ``feature_flag_backend``,
counts consecutive failures per backend, and emits transition events:

* On the third consecutive failure: ``entity.flag.backend.unhealthy``
  with the latest reason.
* On the first success after an unhealthy run:
  ``entity.flag.backend.healthy``.

The prober keeps state in process memory; a future replacement that
persists state to ``feature_flag_backend_registrations`` per design.md
plugs into the same public surface.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.flags.backend_router import (
    list_registered_backends,
)
from automojo.pychestrate.webservice.identity.flags.events import FlagEventTopics
from automojo.pychestrate.webservice.identity.flags.factories.feature_flag_backend import (
    BackendHealth,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish


logger = logging.getLogger(__name__)


UNHEALTHY_FAILURE_THRESHOLD: int = 3


@dataclass
class _BackendHealthState:
    """
        Mutable health state per backend.

        :param backend_name: Backend identifier.
        :param consecutive_failures: Count of failed probes since the
                                     last success.
        :param marked_unhealthy: True after the threshold has been hit
                                 and ``unhealthy`` was emitted.
        :param last_reason: Latest failure reason captured.
    """
    backend_name: str
    consecutive_failures: int
    marked_unhealthy: bool
    last_reason: str


_PROBER_LOCK = threading.RLock()
_HEALTH_STATE: Dict[str, _BackendHealthState] = {}


def _get_or_init_state(*, backend_name: str) -> _BackendHealthState:
    """
        Return the per-backend state, creating it on first observation.

        :param backend_name: Backend identifier.

        :returns: :class:`_BackendHealthState` row.
    """
    state = _HEALTH_STATE.get(backend_name, None)
    if state is None:
        state = _BackendHealthState(
            backend_name=backend_name,
            consecutive_failures=0,
            marked_unhealthy=False,
            last_reason="",
        )
        _HEALTH_STATE[backend_name] = state
    rtnval = state
    return rtnval


def _emit_unhealthy(*, backend_name: str, reason: str) -> None:
    """
        Publish ``entity.flag.backend.unhealthy``.

        :param backend_name: Backend identifier.
        :param reason: Reason string from :class:`BackendHealth`.

        :returns: None.
    """
    now = utc_now()
    payload = {
        "backend_name": backend_name,
        "reason": reason,
        "at": now.isoformat(),
    }
    event = EntityEvent(
        topic=FlagEventTopics.BACKEND_UNHEALTHY,
        payload=payload,
        source_event_id=new_uuid(),
    )
    publish(event=event)
    logger.warning(
        "flag.backend.unhealthy backend=%s reason=%s", backend_name, reason
    )
    return


def _emit_healthy(*, backend_name: str) -> None:
    """
        Publish ``entity.flag.backend.healthy``.

        :param backend_name: Backend identifier.

        :returns: None.
    """
    now = utc_now()
    payload = {
        "backend_name": backend_name,
        "at": now.isoformat(),
    }
    event = EntityEvent(
        topic=FlagEventTopics.BACKEND_HEALTHY,
        payload=payload,
        source_event_id=new_uuid(),
    )
    publish(event=event)
    logger.info("flag.backend.healthy backend=%s", backend_name)
    return


def probe_once() -> List[Tuple[str, BackendHealth]]:
    """
        Probe every registered backend exactly once, updating per-backend
        consecutive-failure counters and emitting transition events.

        Idempotent for callers — invoking on a cadence is the intended
        usage. Each probe error is captured rather than raised so a
        misbehaving backend cannot starve the others.

        :returns: List of (backend_name, BackendHealth) pairs in
                  registration order. ``BackendHealth`` reports the raw
                  outcome of this probe call.
    """
    results: List[Tuple[str, BackendHealth]] = []
    with _PROBER_LOCK:
        for backend_cls in list_registered_backends():
            backend_name = backend_cls.backend_name()
            health = _safe_health_check(backend_cls=backend_cls)
            results.append((backend_name, health))

            state = _get_or_init_state(backend_name=backend_name)
            if health.healthy is True:
                if state.marked_unhealthy is True:
                    _emit_healthy(backend_name=backend_name)
                state.consecutive_failures = 0
                state.marked_unhealthy = False
                state.last_reason = ""
                continue

            state.consecutive_failures += 1
            state.last_reason = health.reason
            if state.consecutive_failures >= UNHEALTHY_FAILURE_THRESHOLD and state.marked_unhealthy is False:
                state.marked_unhealthy = True
                _emit_unhealthy(backend_name=backend_name, reason=health.reason)

    rtnval = results
    return rtnval


def _safe_health_check(*, backend_cls) -> BackendHealth:
    """
        Call ``backend_cls.health_check()``, reclassifying any raised
        exception as an unhealthy result. Per AGENTS.md this is a
        purposeful, contextual catch — the prober's job is to convert
        backend faults into observable health transitions.

        :param backend_cls: Backend implementation class.

        :returns: :class:`BackendHealth`.
    """
    try:
        rtnval = backend_cls.health_check()
    except Exception as xcpt:  # noqa: BLE001 — purposeful prober isolation
        logger.exception(
            "flag.backend.health_check_failed backend=%s error=%s",
            backend_cls.backend_name(), xcpt
        )
        rtnval = BackendHealth(healthy=False, reason="health_check_raised:{}".format(type(xcpt).__name__))
    return rtnval


def get_state(*, backend_name: str) -> Optional[_BackendHealthState]:
    """
        Return the current state row for ``backend_name`` if observed.

        :param backend_name: Backend identifier.

        :returns: :class:`_BackendHealthState` or None.
    """
    with _PROBER_LOCK:
        rtnval = _HEALTH_STATE.get(backend_name, None)
    return rtnval


def reset_for_testing() -> None:
    """
        Discard per-backend health state.

        :returns: None.
    """
    with _PROBER_LOCK:
        _HEALTH_STATE.clear()
    return
