"""
.. module:: messaging.outbox
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Transactional outbox helper for publishing entity events.

.. moduleauthor:: Code Craft AI LLC

Entity events must land on the bus only after the row that describes them
has committed. This helper buffers events against a SQLAlchemy session
and flushes them to the bus inside an ``after_commit`` hook. If the
transaction rolls back, the buffered events are dropped. The
implementation is deliberately tiny: when the full ``0-persistence``
outbox table lands, the public functions here are what callers keep
using.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, publish


_SESSION_EVENT_ATTR = "_pychestrate_outbox_events"


def enqueue_event(*, db_session: DbSession, event: EntityEvent) -> None:
    """
        Buffer an entity event against the session's pending commit.

        :param db_session: The active SQLAlchemy session whose commit will publish.
        :param event: The event to buffer for post-commit delivery.

        :returns: None.
    """
    pending: List[EntityEvent]
    pending = getattr(db_session, _SESSION_EVENT_ATTR, None)
    if pending is None:
        pending = []
        setattr(db_session, _SESSION_EVENT_ATTR, pending)
        _attach_commit_hook(db_session=db_session)

    pending.append(event)

    return


def _attach_commit_hook(*, db_session: DbSession) -> None:
    """
        Attach the after-commit and after-rollback listeners to the session.

        :param db_session: The active SQLAlchemy session.

        :returns: None.
    """

    def _after_commit(session: DbSession) -> None:
        pending: List[EntityEvent]
        pending = getattr(session, _SESSION_EVENT_ATTR, [])
        setattr(session, _SESSION_EVENT_ATTR, [])
        for evt in pending:
            publish(event=evt)
        return

    def _after_rollback(session: DbSession) -> None:
        setattr(session, _SESSION_EVENT_ATTR, [])
        return

    sqla_event.listen(db_session, "after_commit", _after_commit)
    sqla_event.listen(db_session, "after_rollback", _after_rollback)

    return


def drain_pending_for_testing(*, db_session: DbSession) -> List[EntityEvent]:
    """
        Pop and return all pending events without publishing them. Test-only.

        :param db_session: The active SQLAlchemy session.

        :returns: The list of events that were buffered at call time.
    """
    pending: List[EntityEvent]
    pending = getattr(db_session, _SESSION_EVENT_ATTR, [])
    setattr(db_session, _SESSION_EVENT_ATTR, [])
    return list(pending)
