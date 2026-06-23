"""
.. module:: projects.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus subscribers owned by 2-projects.

.. moduleauthor:: Code Craft AI LLC

Wires the ``entity.user.deleted`` bus topic (emitted by 1-user-management
when a user is hard-deleted) to cascade :class:`ProjectMemberBinding`
removal. Service startup calls :func:`wire_bus_subscribers` once after
Phase-1/Phase-2 extensions are registered.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe
from ccai.pychestrate.webservice.projects import service as project_service


SessionFactory = Callable[[], DbSession]

USER_DELETED_TOPIC: str = "entity.user.deleted"


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register the ``entity.user.deleted`` subscriber. The handler opens
        a fresh session from ``session_factory`` so the cascade runs
        outside the originating request transaction.

        :param session_factory: Callable returning a new SQLAlchemy session.

        :returns: None.
    """
    subscribe(
        topic=USER_DELETED_TOPIC,
        subscriber=_build_user_deleted_handler(session_factory=session_factory),
    )
    return


def _build_user_deleted_handler(*, session_factory: SessionFactory):
    """
        Build the closure that cascades member-binding removal.
    """

    def _handler(event: EntityEvent) -> None:
        user_id = event.payload.get("user_id", None)
        if user_id is None:
            return

        session = session_factory()
        try:
            project_service.cascade_user_deleted(
                db_session=session, user_id=user_id,
            )
        finally:
            session.close()
        return

    return _handler
