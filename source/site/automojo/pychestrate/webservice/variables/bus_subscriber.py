"""
.. module:: variables.bus_subscriber
    :synopsis: Bus subscribers for 2-global-variables cascade cleanup.

When a project is deleted, every variable binding scoped at
``VariableScope.PROJECT`` for that project becomes orphan
storage. This subscriber consumes ``entity.project.deleted``
and walks the project's bindings, deleting each one and
emitting :data:`VariableEventTopics.VARIABLE_UNSET` per
purged row so downstream caches and audit subscribers see
the implicit unset.

The subscriber holds no DB session of its own — the bootstrap
hands in a session-factory callable so each cascade runs in
its own transaction outside the originating
``project.delete`` request.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.variables import (
    repository as variable_repository,
)
from automojo.pychestrate.webservice.variables.events import (
    VariableEventTopics,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
)


SessionFactory = Callable[[], DbSession]


_LOCK = threading.RLock()
_INSTALLED: bool = False


def reset_for_testing() -> None:
    """
        Drop the install latch so tests can re-wire from
        scratch on every case.
    """
    global _INSTALLED
    with _LOCK:
        _INSTALLED = False
    return


def wire_bus_subscribers(
        *,
        session_factory: SessionFactory
    ) -> None:
    """
        Subscribe :func:`_handle_project_deleted` to the
        ``entity.project.deleted`` topic. Idempotent — second
        installation is a no-op so the bootstrap helper can
        be called safely on every startup.
    """
    global _INSTALLED
    with _LOCK:
        if _INSTALLED is True:
            return
        _INSTALLED = True
    subscribe(
        topic="entity.project.deleted",
        subscriber=_build_handler(session_factory=session_factory),
    )
    return


def cascade_project_deleted(
        *,
        db_session: DbSession,
        project_id: str,
        actor_user_id: Optional[str] = None
    ) -> int:
    """
        Purge every PROJECT-scoped variable binding for
        ``project_id`` and emit
        :data:`VariableEventTopics.VARIABLE_UNSET` per row.
        Returns the count of bindings removed.
    """
    bindings = variable_repository.list_for_scope(
        db_session=db_session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
    )
    if bindings is None or len(bindings) == 0:
        return 0
    purged = 0
    for binding in bindings:
        name = binding.name
        variable_repository.delete_binding(
            db_session=db_session, binding=binding,
        )
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=VariableEventTopics.VARIABLE_UNSET,
                payload={
                    "scope": VariableScope.PROJECT.value,
                    "scope_id": project_id,
                    "name": name,
                    "actor_user_id": actor_user_id,
                    "reason": "project_deleted",
                    "purged_at": utc_now().isoformat(),
                },
                source_event_id=new_uuid(),
            ),
        )
        purged = purged + 1
    db_session.commit()
    return purged


def _build_handler(*, session_factory: SessionFactory):
    """
        Build the per-event handler closure. Each invocation
        opens a fresh session via ``session_factory`` so the
        cascade runs outside the originating
        project.delete request transaction.
    """

    def _handler(event: EntityEvent) -> None:
        project_id = _extract_project_id(payload=event.payload)
        if project_id is None:
            return
        actor_user_id = None
        if event.payload is not None:
            actor_user_id = event.payload.get("actor_user_id")
        session = session_factory()
        try:
            cascade_project_deleted(
                db_session=session,
                project_id=project_id,
                actor_user_id=actor_user_id,
            )
        finally:
            session.close()
        return

    return _handler


def _extract_project_id(*, payload) -> Optional[str]:
    if payload is None:
        return None
    rtnval = payload.get("project_id")
    if rtnval is None:
        return None
    return str(rtnval)
