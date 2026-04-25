"""
.. module:: system_health.extensions.message_bus_probe
    :synopsis: MessageBusHealthProbe — readiness probe over the in-process bus.

The probe publishes a synthetic event on a private topic and
verifies that a subscribed listener receives it. Round-trip
delivery proves the bus is accepting publishes and dispatching
to subscribers — the two failure modes a worker pod cares
about.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading
import time

from datetime import datetime, timezone
from typing import List

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
    subscribe,
    unsubscribe,
)
from automojo.pychestrate.webservice.system_health.extensions.probe import (
    SystemHealthProbeExtension,
)
from automojo.pychestrate.webservice.system_health.registry import (
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    truncate_last_error,
)


BUS_HEALTH_TOPIC: str = "system_health.bus.ping"


class MessageBusHealthProbe(SystemHealthProbeExtension):
    """
        Readiness probe that round-trips a synthetic
        :class:`EntityEvent` through the in-process bus and
        confirms a subscribed listener receives it. Returns
        ``FAIL`` when the publish raises or the listener does
        not record the synthetic event id.
    """
    resource_extension_name: str = "system_health_probe"

    name: str = "message_bus"
    kind: ProbeKind = ProbeKind.READINESS
    interval_seconds: float = 10.0
    timeout_seconds: float = 1.0

    @classmethod
    def run_probe(cls) -> ProbeResult:
        observed_at = datetime.now(tz=timezone.utc)
        monotonic_start = time.monotonic()
        received: List[str] = []
        synthetic_id = new_uuid()

        def _listener(event: EntityEvent) -> None:
            if event.payload.get("synthetic_id") == synthetic_id:
                received.append(synthetic_id)
            return

        subscribe(topic=BUS_HEALTH_TOPIC, subscriber=_listener)
        try:
            try:
                publish(
                    event=EntityEvent(
                        topic=BUS_HEALTH_TOPIC,
                        payload={"synthetic_id": synthetic_id},
                        source_event_id=new_uuid(),
                    ),
                )
            except Exception as publish_err:
                elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
                rtnval = ProbeResult(
                    status=ProbeStatus.FAIL,
                    duration_ms=elapsed_ms,
                    observed_at=datetime.now(tz=timezone.utc),
                    last_error=truncate_last_error(
                        message="{}: {}".format(
                            type(publish_err).__name__, publish_err,
                        ),
                    ),
                )
                return rtnval
        finally:
            unsubscribe(topic=BUS_HEALTH_TOPIC, subscriber=_listener)

        elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
        if synthetic_id not in received:
            rtnval = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error="bus_round_trip_failed",
            )
            return rtnval
        rtnval = ProbeResult(
            status=ProbeStatus.OK,
            duration_ms=elapsed_ms,
            observed_at=datetime.now(tz=timezone.utc),
        )
        return rtnval
