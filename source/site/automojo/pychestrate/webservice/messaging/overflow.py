"""
.. module:: messaging.overflow
    :synopsis: Bounded subscriber queue with overflow policies.

The M2 message bus dispatches each event to a per-subscriber
queue. The queue's ``maxsize`` plus its overflow policy
controls what happens when a slow subscriber falls behind:

* :data:`OverflowPolicy.DROP_OLDEST` — drop the head of the
  queue and append the new event. The subscriber sees the
  newest events; the oldest are sacrificed. Suited for
  monitoring streams where freshness matters more than
  completeness.
* :data:`OverflowPolicy.DROP_NEWEST` — keep the queue intact
  and drop the new event. The subscriber sees a stable
  prefix; the *latest* events are sacrificed. Suited for
  retry / repair pipelines where the early entries are the
  most actionable.
* :data:`OverflowPolicy.BLOCK_PUBLISHER` — block the publish
  call until a slot frees. Suited for system-of-record
  paths where backpressure must propagate. The bounded
  helper exposes a non-blocking ``try_offer`` for tests so
  callers don't need real threads to exercise the policy.

The ``BoundedQueue`` is a pure data structure: thread-safety
is the caller's responsibility. The M2 dispatcher wraps it
in a per-subscriber lock + worker thread; tests exercise
the queue directly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, List, Optional


class OverflowPolicy(str, enum.Enum):
    """
        Policy applied when a bounded queue fills up.
    """
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    BLOCK_PUBLISHER = "block_publisher"


@dataclass(frozen=True)
class OfferOutcome:
    """
        Result of a queue ``offer`` call.

        :param accepted: ``True`` when the new event landed
                         in the queue.
        :param dropped: ``True`` when an event was sacrificed
                        (oldest or newest depending on
                        policy).
        :param dropped_event: The event that was sacrificed,
                              or ``None``.
        :param would_block: ``True`` when the policy is
                            ``BLOCK_PUBLISHER`` and the queue
                            is full — the bounded helper
                            does not block; the dispatcher
                            wraps it in a real waiter.
    """
    accepted: bool
    dropped: bool = False
    dropped_event: Optional[Any] = None
    would_block: bool = False


class BoundedQueue:
    """
        Bounded FIFO queue with a configurable overflow
        policy.
    """

    def __init__(
            self,
            *,
            maxsize: int,
            policy: OverflowPolicy
        ) -> None:
        if maxsize <= 0:
            err_lines = ["BoundedQueue maxsize must be >= 1."]
            err_lines.append("VALUE: {}".format(maxsize))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        self._maxsize: int = maxsize
        self._policy: OverflowPolicy = policy
        self._buffer: Deque[Any] = deque()
        return

    def maxsize(self) -> int:
        """
            Return the configured maxsize.
        """
        rtnval = self._maxsize
        return rtnval

    def policy(self) -> OverflowPolicy:
        """
            Return the configured overflow policy.
        """
        rtnval = self._policy
        return rtnval

    def size(self) -> int:
        """
            Return the current number of buffered events.
        """
        rtnval = len(self._buffer)
        return rtnval

    def is_full(self) -> bool:
        """
            Return ``True`` when the queue is at maxsize.
        """
        rtnval = len(self._buffer) >= self._maxsize
        return rtnval

    def is_empty(self) -> bool:
        """
            Return ``True`` when the queue is empty.
        """
        rtnval = len(self._buffer) == 0
        return rtnval

    def snapshot(self) -> List[Any]:
        """
            Return a list copy of the buffered events. Used
            by tests; the dispatcher walks ``pop_oldest``
            instead.
        """
        rtnval = list(self._buffer)
        return rtnval

    def pop_oldest(self) -> Optional[Any]:
        """
            Remove and return the head of the queue, or
            ``None`` when empty.
        """
        if len(self._buffer) == 0:
            return None
        rtnval = self._buffer.popleft()
        return rtnval

    def offer(self, *, event: Any) -> OfferOutcome:
        """
            Try to insert ``event``. Honors the configured
            overflow policy. The :data:`OverflowPolicy.BLOCK_PUBLISHER`
            path returns ``OfferOutcome(would_block=True)``
            instead of blocking — callers wrap it in a real
            waiter for the production path.
        """
        if not self.is_full():
            self._buffer.append(event)
            rtnval = OfferOutcome(accepted=True)
            return rtnval

        if self._policy == OverflowPolicy.DROP_OLDEST:
            dropped = self._buffer.popleft()
            self._buffer.append(event)
            rtnval = OfferOutcome(
                accepted=True,
                dropped=True,
                dropped_event=dropped,
            )
            return rtnval
        if self._policy == OverflowPolicy.DROP_NEWEST:
            rtnval = OfferOutcome(
                accepted=False,
                dropped=True,
                dropped_event=event,
            )
            return rtnval
        if self._policy == OverflowPolicy.BLOCK_PUBLISHER:
            rtnval = OfferOutcome(
                accepted=False,
                would_block=True,
            )
            return rtnval

        # Unknown policy — fail closed by rejecting.
        rtnval = OfferOutcome(
            accepted=False,
            dropped=True,
            dropped_event=event,
        )
        return rtnval

    def try_offer(self, *, event: Any) -> bool:
        """
            Convenience wrapper that returns the boolean
            ``accepted`` flag — useful for the BLOCK_PUBLISHER
            test surface that polls until acceptance.
        """
        outcome = self.offer(event=event)
        rtnval = outcome.accepted
        return rtnval
