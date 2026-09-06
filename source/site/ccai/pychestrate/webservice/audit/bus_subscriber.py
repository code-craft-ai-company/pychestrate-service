"""
.. module:: audit.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bridges entity.* topics into audit capture calls.

.. moduleauthor:: Code Craft AI LLC

The subscriber registers one callback per ``source_topic`` declared by an
``AuditEventTypeExtension``. When the in-process bus delivers an event,
the subscriber invokes :func:`capture_event` against the caller-supplied
session factory. The session factory is injected so the subscriber stays
testable without importing the request context directly.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.audit.audit_writer import capture_event
from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


SessionFactory = Callable[[], DbSession]


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register a subscriber for every known ``source_topic`` in the
        registered audit event catalog. The handler runs inside a fresh
        session produced by ``session_factory`` so the audit insert lands
        outside the originating request's transaction.

        :param session_factory: Callable returning a new SQLAlchemy session.

        :returns: None.
    """
    packs = list_resource_extensions(base_class=AuditEventTypeExtension)
    topic_to_kind: Dict[str, str] = {}
    for pack in packs:
        topic_to_kind[pack.source_topic] = pack.kind

    for topic, kind in topic_to_kind.items():
        # Idempotent: the phase-1 and phase-2 bootstraps both call this
        # (the phase-2 pass picks up audit kinds registered after phase
        # 1). Wiring a topic twice would insert every audit record twice
        # and the second insert violates the ``source_event_id`` unique
        # constraint, so a topic whose handler is still subscribed is
        # skipped. A bus reset (tests) drops the handler and the topic
        # is wired again.
        # The guard is keyed by (topic, session factory): the same
        # factory wired twice is a no-op, while a test harness that
        # supplies its own factory still gets a handler writing to its
        # database.
        already = False
        for wired_factory, wired_handler in _WIRED_HANDLERS.get(topic, []):
            if wired_factory is session_factory and _is_subscribed(topic=topic, subscriber=wired_handler):
                already = True
                break
        if already:
            continue
        handler = _build_handler(session_factory=session_factory, kind=kind, topic=topic)
        subscribe(topic=topic, subscriber=handler)
        _WIRED_HANDLERS.setdefault(topic, []).append((session_factory, handler))

    return


#: ``topic -> [(session_factory, handler), ...]`` for every subscriber
#: this module has wired.
_WIRED_HANDLERS: Dict[str, List[Tuple[Any, Callable[[EntityEvent], None]]]] = {}


def _is_subscribed(*, topic: str, subscriber: Callable[[EntityEvent], None]) -> bool:
    """
        Whether ``subscriber`` is currently registered on the bus for
        ``topic``. Falls back to ``False`` (re-wire) when the bus does not
        expose its registry.
    """
    try:
        from ccai.pychestrate.webservice.messaging import event_bus as _bus  # noqa: E402
        registry = getattr(_bus, "_SUBSCRIBERS", None)
        if registry is None:
            return False
        bucket = registry.get(topic, [])
        rtnval = any(candidate is subscriber for candidate in bucket)
        return rtnval
    except Exception:
        return False


def reset_wiring_for_testing() -> None:
    """
        Forget every handler this module wired (tests reset the bus too).
    """
    _WIRED_HANDLERS.clear()
    return


def _build_handler(
        *,
        session_factory: SessionFactory,
        kind: str,
        topic: str
    ):
    """
        Return a closure that captures the event into audit under the given kind.

        :param session_factory: Callable returning a new SQLAlchemy session.
        :param kind: Audit kind registered for ``topic``.
        :param topic: Originating bus topic.

        :returns: A callable suitable for :func:`subscribe`.
    """

    def _handler(event: EntityEvent) -> None:
        session = session_factory()
        try:
            payload = dict(event.payload)
            actor_user_id = payload.get("actor_user_id", None)
            target_ref = payload.get("target_ref", None)
            capture_event(
                db_session=session,
                source_event_id=event.source_event_id,
                source_topic=topic,
                kind=kind,
                actor_user_id=actor_user_id,
                actor_service_identity=None,
                target_ref=target_ref,
                payload=payload,
            )
            session.commit()
        finally:
            session.close()
        return

    return _handler
