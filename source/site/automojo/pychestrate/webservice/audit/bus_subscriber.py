"""
.. module:: audit.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bridges entity.* topics into audit capture calls.

.. moduleauthor:: Automation Mojo LLC

The subscriber registers one callback per ``source_topic`` declared by an
``AuditEventTypeExtension``. When the in-process bus delivers an event,
the subscriber invokes :func:`capture_event` against the caller-supplied
session factory. The session factory is injected so the subscriber stays
testable without importing the request context directly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable, Dict

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.audit.audit_writer import capture_event
from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from automojo.pychestrate.webservice.extensions.registry import list_resource_extensions
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


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
        subscribe(
            topic=topic,
            subscriber=_build_handler(
                session_factory=session_factory, kind=kind, topic=topic
            ),
        )

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
