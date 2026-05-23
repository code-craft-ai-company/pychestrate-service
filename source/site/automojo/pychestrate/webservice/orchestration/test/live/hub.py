"""
.. module:: orchestration.test.live.hub
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: LiveRunHub — registry of per-run relays.

.. moduleauthor:: Automation Mojo LLC

The hub is a process-singleton that lazily constructs a
:class:`RunRelay` per run on first publish. The SSE route (M2)
calls :meth:`subscribe_sse` to attach a streaming response to a
relay; M1 ships :meth:`subscribe_callable` so tests can attach
plain callables without a running web app.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional

from automojo.pychestrate.webservice.orchestration.test.live.relay import RunRelay
from automojo.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
    ProgressSnapshot,
)


class LiveRunHub:
    """
        Process-singleton-friendly hub over per-run relays.
    """

    def __init__(self) -> None:
        self._relays: Dict[str, RunRelay] = {}
        self._lock: threading.RLock = threading.RLock()
        return

    def get_or_create_relay(
            self,
            *,
            run_id: str,
            project_id: str
        ) -> RunRelay:
        """
            Return the relay for ``run_id``, constructing one on
            first call. Subsequent calls with the same ``run_id``
            ignore the project_id parameter (the relay is bound
            on construction).
        """
        with self._lock:
            existing = self._relays.get(run_id)
            if existing is not None:
                return existing
            relay = RunRelay(run_id=run_id, project_id=project_id)
            self._relays[run_id] = relay
            return relay

    def find_relay(self, *, run_id: str) -> Optional[RunRelay]:
        """
            Return the relay for ``run_id`` or ``None``.
        """
        with self._lock:
            rtnval = self._relays.get(run_id)
        return rtnval

    def publish(
            self,
            *,
            run_id: str,
            project_id: str,
            kind: str,
            payload: Mapping[str, Any],
            recorded_at: Optional[datetime] = None
        ) -> ProgressEvent:
        """
            Convenience helper: get-or-create the relay and
            publish a :class:`ProgressEvent` to it.
        """
        relay = self.get_or_create_relay(run_id=run_id, project_id=project_id)
        when = recorded_at
        if when is None:
            when = datetime.now(timezone.utc)
        event = ProgressEvent(
            run_id=run_id,
            project_id=project_id,
            kind=kind,
            payload=dict(payload),
            recorded_at=when,
            sequence=0,
        )
        rtnval = relay.publish(event=event)
        return rtnval

    def subscribe_callable(
            self,
            *,
            run_id: str,
            project_id: str,
            callback: Callable[[ProgressEvent], None]
        ) -> Callable[[], None]:
        """
            Attach a plain callable subscriber to the relay for
            ``run_id``. Returns an unsubscribe callable.
        """
        relay = self.get_or_create_relay(run_id=run_id, project_id=project_id)
        rtnval = relay.subscribe(callback=callback)
        return rtnval

    def snapshot_for(
            self,
            *,
            run_id: str
        ) -> Optional[ProgressSnapshot]:
        """
            Return the latest snapshot for ``run_id`` or
            ``None`` when no relay exists.
        """
        relay = self.find_relay(run_id=run_id)
        if relay is None:
            return None
        rtnval = relay.snapshot()
        return rtnval

    def reset_for_testing(self) -> None:
        """
            Clear every relay. Tests call this between cases.
        """
        with self._lock:
            self._relays = {}
        return
