"""
.. module:: tagging.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus subscribers for 2-tagging M3 orphan cleanup.

.. moduleauthor:: Code Craft AI LLC

Subscribes to ``entity.*.deleted`` / ``entity.*.deregistered`` / run
terminal topics and drops any :class:`TagAssignment` rows that point at
the removed entity. Idempotent — no-ops if no rows match.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable, Mapping

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe
from ccai.pychestrate.webservice.tagging import repository as tag_repository


SessionFactory = Callable[[], DbSession]


_TOPIC_TO_KIND: Mapping[str, str] = {
    "entity.project.deleted": "project",
    "entity.resource.deregistered": "resource",
    "entity.pod.deregistered": "pod",
    "entity.run.completed": "job",
    "entity.run.failed": "job",
    "entity.run.cancelled": "job",
}


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register subscribers for every known orphan-producing topic.

        :param session_factory: Callable returning a fresh session.

        :returns: None.
    """
    for topic, kind in _TOPIC_TO_KIND.items():
        subscribe(
            topic=topic,
            subscriber=_build_handler(
                session_factory=session_factory, kind=kind,
            ),
        )
    return


def _build_handler(*, session_factory: SessionFactory, kind: str):
    """
        Build the per-topic delete handler.
    """

    def _handler(event: EntityEvent) -> None:
        entity_id = _extract_entity_id(payload=event.payload, kind=kind)
        if entity_id is None:
            return

        session = session_factory()
        try:
            tag_repository.delete_for_entity(
                db_session=session, entity_kind=kind, entity_id=entity_id,
            )
            session.commit()
        finally:
            session.close()
        return

    return _handler


def _extract_entity_id(*, payload: Mapping, kind: str) -> str:
    """
        Resolve the entity id from an event payload using kind-specific keys.
    """
    if kind == "project":
        return payload.get("project_id", None)
    if kind == "resource":
        return payload.get("resource_id", None)
    if kind == "pod":
        return payload.get("pod_id", None)
    if kind == "job":
        return payload.get("run_id", None) or payload.get("job_id", None)
    return None
