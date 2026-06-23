"""
.. module:: jobs.run.state.outbox_publisher
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Drain unpublished run-state outbox rows onto the bus.

.. moduleauthor:: Code Craft AI LLC

Every successful :func:`RunStateMachine.transition` writes a row to
``runs_run_event_outbox`` *and* fires the in-process bus via
:mod:`messaging.outbox`. For crash recovery (process dies between
commit and publish) the durable outbox table exists; the drainer in
this module reads every row whose ``published_at`` is still ``None``
and re-publishes, then marks them as published.

M1 provides :func:`drain_once` as a blocking helper that runs a
single batch. A long-running daemon that loops on a timer is M2
scope. Service startup can call ``drain_once`` once to recover any
events that were buffered during a crashed previous process — that
alone is sufficient for the "events are never lost" guarantee.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.run.state import repository
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, publish


def drain_once(
        *,
        db_session: DbSession,
        batch_size: int = 256
    ) -> int:
    """
        Publish every unpublished run-state outbox row in one batch.

        Each row is sent to the in-process bus via
        :func:`messaging.event_bus.publish` (bypassing the session
        outbox since we're already past-commit for the original
        transactions). After publish, the rows are marked
        ``published_at`` in a single UPDATE and the session commits.

        :param db_session: Active SQLAlchemy session. The drainer
                           uses this session for both read and mark-
                           published write so callers control the
                           isolation boundary.
        :param batch_size: Max rows to drain in one call. Defaults
                           to 256.

        :returns: Number of rows published.
    """
    rows = repository.list_unpublished_outbox_rows(
        db_session=db_session,
        limit=batch_size,
    )
    if len(rows) == 0:
        return 0

    outbox_ids: List[str] = []
    for row in rows:
        payload = dict(row.payload or {})
        publish(
            event=EntityEvent(
                topic=row.topic,
                payload=payload,
                source_event_id=new_uuid(),
            ),
        )
        outbox_ids.append(row.outbox_id)

    now = utc_now()
    repository.mark_outbox_published(
        db_session=db_session,
        outbox_ids=outbox_ids,
        published_at=now,
    )
    db_session.commit()

    rtnval = len(outbox_ids)
    return rtnval
