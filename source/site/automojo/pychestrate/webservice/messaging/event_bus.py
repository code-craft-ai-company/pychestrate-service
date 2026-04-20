"""
.. module:: messaging.event_bus
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-process pub/sub stub for entity events.

.. moduleauthor:: Automation Mojo LLC

This module exposes a minimal synchronous event bus used by the Layer 1
features to publish ``entity.*`` topics. Subscribers are registered per
topic by the :func:`subscribe` call. The implementation is intentionally
simple — a thread-safe dict of topic → subscriber list — so it can be
replaced by the full ``0-message-bus`` feature without changing callers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Tuple


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityEvent:
    """
        A published entity event.

        :param topic: Dotted topic string (``entity.user.created``).
        :param payload: Opaque mapping describing the event.
        :param source_event_id: Stable UUID string used by downstream dedup.
    """
    topic: str
    payload: Mapping[str, Any]
    source_event_id: str


Subscriber = Callable[[EntityEvent], None]


_BUS_LOCK = threading.RLock()
_SUBSCRIBERS: Dict[str, List[Subscriber]] = {}


def subscribe(*, topic: str, subscriber: Subscriber) -> None:
    """
        Register a subscriber for a topic.

        :param topic: Topic string (exact match; wildcards are not supported in
                      the stub).
        :param subscriber: Callable that receives published events.

        :returns: None.
    """
    with _BUS_LOCK:
        bucket = _SUBSCRIBERS.setdefault(topic, [])
        bucket.append(subscriber)

    return


def unsubscribe(*, topic: str, subscriber: Subscriber) -> None:
    """
        Remove a previously registered subscriber.

        :param topic: Topic the subscriber was registered against.
        :param subscriber: The callable that was registered.

        :returns: None.
    """
    with _BUS_LOCK:
        bucket = _SUBSCRIBERS.get(topic, None)
        if bucket is None:
            return
        if subscriber in bucket:
            bucket.remove(subscriber)

    return


def publish(*, event: EntityEvent) -> None:
    """
        Deliver an event synchronously to every registered subscriber.

        Each subscriber's exceptions are logged and suppressed so that a
        faulted subscriber cannot block delivery to other subscribers. Per
        AGENTS.md this is an explicit, purposeful catch: we capture the
        failure, emit a structured log, and continue.

        :param event: The event to deliver.

        :returns: None.
    """
    with _BUS_LOCK:
        snapshot: Tuple[Subscriber, ...] = tuple(_SUBSCRIBERS.get(event.topic, []))

    for subscriber in snapshot:
        try:
            subscriber(event)
        except Exception as xcpt:  # noqa: BLE001 — purposeful subscriber isolation
            logger.exception(
                "event_bus.subscriber_failed topic=%s subscriber=%s error=%s",
                event.topic, subscriber, xcpt
            )

    return


def reset_for_testing() -> None:
    """
        Clear all subscribers. Test-only helper.

        :returns: None.
    """
    with _BUS_LOCK:
        _SUBSCRIBERS.clear()

    return
