"""
.. module:: metrics.ingest.bus_bridge
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: MetricIngestBusBridge -- feeds the registered metric
               extensions from the in-process event bus.

.. moduleauthor:: Code Craft AI LLC

Each registered :class:`MetricDefinitionExtension` names the
``entity.*`` topic it measures (``source_topic``). The bridge
subscribes one handler per distinct topic; when an event on that
topic is published it opens a session and emits one sample per
matching extension through :func:`emit_metric_for_event`.

This is the production metric writer the Timeseries, Dashboards, SLO
and alert-rule views read from (audit ORC-04): before it was wired,
the metric extensions were declared but nothing ever wrote a sample.
A failing emission (a label that does not match the declaration, a
cardinality cap) is logged and skipped so one bad event never breaks
the publisher that raised it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from typing import Callable, List, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
    unsubscribe,
)
from ccai.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
)
from ccai.pychestrate.webservice.metrics.ingest.service import (
    emit_metric_for_event,
)


SessionFactory = Callable[[], DbSession]


_LOGGER = logging.getLogger("pychestrate.metrics.ingest.bus_bridge")


class MetricIngestBusBridge:
    """
        Subscribes the registered metric extensions' source topics and
        writes a sample for every matching event.
    """

    def __init__(self, *, session_factory: SessionFactory) -> None:
        """
            :param session_factory: Factory yielding a fresh session;
                                    bus events fire outside a request
                                    scope, so every emission opens its
                                    own session.
        """
        self._session_factory: SessionFactory = session_factory
        self._lock: threading.RLock = threading.RLock()
        self._subscribed_topics: List[str] = []
        return

    def use_session_factory(self, *, session_factory: SessionFactory) -> None:
        """
            Point later emissions at ``session_factory`` (a repeated
            runtime bootstrap hands over its newest factory).

            :param session_factory: Factory yielding a fresh session.

            :returns: None.
        """
        with self._lock:
            self._session_factory = session_factory
        return

    @property
    def subscribed_topics(self) -> Tuple[str, ...]:
        """
            The topics this bridge is subscribed to.
        """
        with self._lock:
            rtnval = tuple(self._subscribed_topics)
        return rtnval

    def attach(self) -> Tuple[str, ...]:
        """
            Subscribe to the source topic of every registered metric
            extension. Idempotent: a topic already subscribed by this
            bridge is not subscribed twice, and extensions registered
            later are picked up by calling again.

            :returns: The topics now subscribed.
        """
        extensions = list_resource_extensions(base_class=MetricDefinitionExtension)
        with self._lock:
            for extension in extensions:
                topic = extension.source_topic()
                if topic in self._subscribed_topics:
                    continue
                subscribe(topic=topic, subscriber=self._on_event)
                self._subscribed_topics.append(topic)
            rtnval = tuple(self._subscribed_topics)
        _LOGGER.info(
            "pychestrate.metrics.ingest.bus_bridge.attached topics=%s",
            ",".join(rtnval),
        )
        return rtnval

    def detach(self) -> None:
        """
            Unsubscribe every topic this bridge subscribed.

            :returns: None.
        """
        with self._lock:
            topics = list(self._subscribed_topics)
            self._subscribed_topics = []
        for topic in topics:
            unsubscribe(topic=topic, subscriber=self._on_event)
        return

    def _on_event(self, event: EntityEvent) -> None:
        """
            Emit one sample per extension whose source topic is the
            event's topic.

            :param event: The published entity event.

            :returns: None.
        """
        matching = self._extensions_for_topic(topic=event.topic)
        if len(matching) == 0:
            return
        payload = dict(event.payload or {})
        with self._lock:
            session_factory = self._session_factory
        session = session_factory()
        try:
            for extension in matching:
                try:
                    emit_metric_for_event(
                        db_session=session,
                        metric_name=extension.metric_name(),
                        event_payload=payload,
                    )
                except Exception as xcpt:  # noqa: BLE001 -- per-emission isolation
                    session.rollback()
                    _LOGGER.warning(
                        "pychestrate.metrics.ingest.emit_failed metric=%s topic=%s error=%s",
                        extension.metric_name(),
                        event.topic,
                        xcpt,
                    )
        finally:
            session.close()
        return

    @staticmethod
    def _extensions_for_topic(*, topic: str) -> List[Type[MetricDefinitionExtension]]:
        """
            The registered extensions measuring ``topic``.

            :param topic: Bus topic.

            :returns: Matching extension classes.
        """
        rtnval: List[Type[MetricDefinitionExtension]] = []
        for extension in list_resource_extensions(base_class=MetricDefinitionExtension):
            if extension.source_topic() == topic:
                rtnval.append(extension)
        return rtnval


__all__ = [
    "MetricIngestBusBridge",
]
