"""
.. module:: orchestration.test.live.relay
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Per-run ring buffer + subscriber set.

.. moduleauthor:: Automation Mojo LLC

A relay is owned by the :class:`LiveRunHub` and lazily
constructed on first event for a run. It keeps the last
``ring_size`` events for replay-since-id and broadcasts every
new event to its subscriber callables.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from collections import deque
from typing import Callable, Deque, List, Optional, Set

from automojo.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
    ProgressSnapshot,
    empty_snapshot,
    merge_event,
)


DEFAULT_RING_SIZE: int = 256


class RunRelay:
    """
        Per-run event broadcaster.

        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param ring_size: Max number of events kept for replay.
    """

    def __init__(
            self,
            *,
            run_id: str,
            project_id: str,
            ring_size: int = DEFAULT_RING_SIZE
        ) -> None:
        self._run_id: str = run_id
        self._project_id: str = project_id
        self._ring: Deque[ProgressEvent] = deque(maxlen=ring_size)
        self._subscribers: Set[Callable[[ProgressEvent], None]] = set()
        self._snapshot: ProgressSnapshot = empty_snapshot(
            run_id=run_id, project_id=project_id,
        )
        self._next_sequence: int = 1
        self._lock: threading.RLock = threading.RLock()
        self._terminal: bool = False
        return

    def run_id(self) -> str:
        return self._run_id

    def snapshot(self) -> ProgressSnapshot:
        """
            Return the current merged snapshot.
        """
        with self._lock:
            rtnval = self._snapshot
        return rtnval

    def history(self) -> List[ProgressEvent]:
        """
            Return a copy of the ring buffer.
        """
        with self._lock:
            rtnval = list(self._ring)
        return rtnval

    def subscribe(
            self,
            *,
            callback: Callable[[ProgressEvent], None]
        ) -> Callable[[], None]:
        """
            Register a subscriber. Returns a callable that
            unregisters the subscriber when invoked. Subscribers
            receive every event published *after* the call to
            :meth:`subscribe`; replay-since-id is the caller's job
            (use :meth:`history`).

            :param callback: Subscriber callable.

            :returns: Unsubscribe callable.
        """
        with self._lock:
            self._subscribers.add(callback)

        def _unsubscribe() -> None:
            with self._lock:
                self._subscribers.discard(callback)
            return

        return _unsubscribe

    def publish(
            self,
            *,
            event: ProgressEvent
        ) -> ProgressEvent:
        """
            Append ``event`` to the ring (assigning a sequence)
            and broadcast it to every subscriber. Subscriber
            exceptions are caught and logged-via-print so a
            misbehaving subscriber does not block delivery to
            others.

            :param event: Event to publish. The relay overwrites
                          ``sequence`` on the returned event.

            :returns: The event with its assigned sequence.
        """
        with self._lock:
            seq = self._next_sequence
            self._next_sequence = self._next_sequence + 1
            stamped = ProgressEvent(
                run_id=event.run_id,
                project_id=event.project_id,
                kind=event.kind,
                payload=event.payload,
                recorded_at=event.recorded_at,
                sequence=seq,
            )
            self._ring.append(stamped)
            self._snapshot = merge_event(snapshot=self._snapshot, event=stamped)
            subscribers_snapshot = list(self._subscribers)

        for callback in subscribers_snapshot:
            try:
                callback(stamped)
            except Exception:
                # Subscribers are third-party callables; never let
                # one block delivery to others. Logged via the
                # bus subscription harness in M2.
                continue
        return stamped

    def emit_terminal(self, *, kind: str = "terminal") -> None:
        """
            Mark the relay closed and notify subscribers with one
            final event. Idempotent.
        """
        from datetime import datetime, timezone
        with self._lock:
            if self._terminal is True:
                return
            self._terminal = True
        self.publish(
            event=ProgressEvent(
                run_id=self._run_id,
                project_id=self._project_id,
                kind=kind,
                payload={},
                recorded_at=datetime.now(timezone.utc),
                sequence=0,
            ),
        )
        return

    def is_terminal(self) -> bool:
        """
            Return whether the relay has been emit_terminal'd.
        """
        with self._lock:
            rtnval = self._terminal
        return rtnval
