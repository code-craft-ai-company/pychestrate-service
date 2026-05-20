"""
.. module:: orchestration.test.live.bus_bridge
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bridge in-process bus events onto the LiveRunHub relays.

.. moduleauthor:: Automation Mojo LLC

The :class:`LiveRunHub` is a pub/sub registry of per-run relays; the
:mod:`messaging.event_bus` is the in-process event bus that the
run-state machine and the progress ingest service publish on. This
module is the glue: it subscribes a small set of bus topics and
forwards each matching event into the owning run's relay so a
streaming SSE subscriber attached to the hub sees run-state changes
and progress frames as they happen.

The bridge is constructed once at service startup (see
``phase6_bootstrap.bootstrap_live_run_view``) and held as a
process-singleton. The bus has no unsubscribe primitive, so the
bridge subscribes exactly once for the lifetime of the process; the
per-connection unsubscribe lives on the hub relay instead.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from automojo.pychestrate.webservice.ingest.progress.events import (
    ProgressEventTopics,
)
from automojo.pychestrate.webservice.jobs.run.state.events import (
    RunStateEventTopics,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)
from automojo.pychestrate.webservice.orchestration.test.live.hub import (
    LiveRunHub,
)


_LOGGER = logging.getLogger("pychestrate.live.bus_bridge")


#: Maps a bus topic onto the relay event ``kind`` the SSE route
#: understands. The route's frame formatter classifies a relay
#: event ``kind`` into one of the OpenAPI ``RunEvent`` event
#: types (``state_changed`` / ``progress`` / ``result_manifest``).
_TOPIC_TO_KIND: Mapping[str, str] = {
    RunStateEventTopics.STATE_CHANGED: "state_changed",
    RunStateEventTopics.COMPLETED: "state_changed",
    RunStateEventTopics.FAILED: "state_changed",
    RunStateEventTopics.CANCELLED: "state_changed",
    RunStateEventTopics.RECONCILED: "state_changed",
    ProgressEventTopics.SUMMARY_LANDED: "progress.summary",
    ProgressEventTopics.RECORD_INGESTED: "progress.record",
    ProgressEventTopics.FRAME_LANDED: "progress.frame",
}


class LiveRunBusBridge:
    """
        Subscribes the run-lifecycle + progress bus topics and
        forwards each event into the owning run's relay on a
        :class:`LiveRunHub`.

        :param hub: The :class:`LiveRunHub` whose relays receive
                    forwarded events.
    """

    def __init__(self, *, hub: LiveRunHub) -> None:
        self._hub: LiveRunHub = hub
        self._attached: bool = False
        return

    def hub(self) -> LiveRunHub:
        """
            Return the :class:`LiveRunHub` this bridge feeds.
        """
        rtnval = self._hub
        return rtnval

    def attach(self) -> None:
        """
            Subscribe every bridged topic on the in-process bus.
            Idempotent — a second call is a no-op so a re-run of
            the bootstrap does not double-subscribe.
        """
        if self._attached is True:
            return

        for topic in _TOPIC_TO_KIND:
            subscribe(topic=topic, subscriber=self._on_bus_event)

        self._attached = True
        _LOGGER.info(
            "pychestrate.live.bus_bridge.attached topics=%d",
            len(_TOPIC_TO_KIND),
        )
        return

    def is_attached(self) -> bool:
        """
            Return whether :meth:`attach` has subscribed the bus.
        """
        rtnval = self._attached
        return rtnval

    def _on_bus_event(self, event: EntityEvent) -> None:
        """
            Bus subscriber callback. Forwards a single
            :class:`EntityEvent` into the owning run's relay.

            :param event: Event delivered by the in-process bus.

            :returns: None.
        """
        kind = _TOPIC_TO_KIND.get(event.topic, None)
        if kind is None:
            return

        payload = event.payload
        if isinstance(payload, Mapping) is False:
            _LOGGER.warning(
                "pychestrate.live.bus_bridge.bad_payload topic=%s",
                event.topic,
            )
            return

        run_id = payload.get("run_id", None)
        if isinstance(run_id, str) is False or len(run_id) == 0:
            return

        project_id = payload.get("project_id", None)
        if isinstance(project_id, str) is False:
            project_id = ""

        recorded_at = _resolve_recorded_at(payload=payload)

        self._hub.publish(
            run_id=run_id,
            project_id=project_id,
            kind=kind,
            payload=dict(payload),
            recorded_at=recorded_at,
        )
        return


def _resolve_recorded_at(*, payload: Mapping[str, Any]) -> datetime:
    """
        Extract a producer timestamp from a bus payload, falling
        back to ``now`` when the payload carries none / a bad value.

        :param payload: Bus event payload mapping.

        :returns: A timezone-aware UTC datetime.
    """
    candidates = ("transitioned_at", "received_at", "recorded_at", "occurred_at")
    for key in candidates:
        raw = payload.get(key, None)
        if isinstance(raw, datetime):
            rtnval = raw
            return rtnval
        if isinstance(raw, str) and len(raw) > 0:
            try:
                rtnval = datetime.fromisoformat(raw)
                return rtnval
            except ValueError:
                continue

    rtnval = datetime.now(timezone.utc)
    return rtnval
