"""
.. module:: housekeeping.leases
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Take, renew and release the lease on a housekeeping task.

.. moduleauthor:: Code Craft AI LLC

A lease is taken with one conditional ``UPDATE`` (the row is free or
already ours) or, for a task that has never run, an ``INSERT`` whose
primary key makes a second concurrent insert fail. Either way the
database decides, so two processes can never both believe they hold
the same lease.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import socket
import threading
import uuid

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.housekeeping.models import HousekeepingLease


MAX_OUTCOME_LENGTH = 512

_HOLDER_LOCK = threading.Lock()
_HOLDER_PID: Optional[int] = None
_HOLDER_ID: Optional[str] = None


def process_holder_id() -> str:
    """
        Return this process's lease-holder identity: the host name, the
        process id and a random token. The identity is rebuilt after a
        fork, so server workers forked from one parent never share it.

        :returns: The holder identity.
    """
    global _HOLDER_PID
    global _HOLDER_ID
    pid = os.getpid()
    with _HOLDER_LOCK:
        if _HOLDER_ID is None or _HOLDER_PID != pid:
            _HOLDER_ID = "{}:{}:{}".format(socket.gethostname(), pid, uuid.uuid4().hex[:12])
            _HOLDER_PID = pid
        rtnval = _HOLDER_ID
    return rtnval


def acquire_lease(
        db_session: DbSession,
        *,
        task_name: str,
        holder_id: str,
        ttl_seconds: float,
        now: Optional[datetime] = None
    ) -> bool:
    """
        Take the lease on ``task_name`` for ``ttl_seconds`` when it is free
        (never taken, released, or lapsed) or already held by ``holder_id``.

        :param db_session: A session used only for lease bookkeeping; this
                           function commits or rolls it back.
        :param task_name: The housekeeping task's name.
        :param holder_id: The identity taking the lease.
        :param ttl_seconds: How long the lease lasts unless renewed.
        :param now: The current time (defaults to now, UTC).

        :returns: ``True`` when ``holder_id`` now holds the lease.
    """
    if now is None:
        now = utc_now()
    expires_at = now + timedelta(seconds=ttl_seconds)

    taken = db_session.execute(
        update(HousekeepingLease)
        .where(HousekeepingLease.task_name == task_name)
        .where(or_(
            HousekeepingLease.expires_at <= now,
            HousekeepingLease.holder_id == holder_id,
        ))
        .values(holder_id=holder_id, expires_at=expires_at, last_started_at=now)
        .execution_options(synchronize_session=False)
    )
    if taken.rowcount == 1:
        db_session.commit()
        rtnval = True
    else:
        # No free row: either the task has never run, or another holder
        # has it. Inserting settles which; the primary key refuses a
        # second row.
        db_session.add(HousekeepingLease(
            task_name=task_name,
            holder_id=holder_id,
            expires_at=expires_at,
            last_started_at=now,
        ))
        try:
            db_session.commit()
            rtnval = True
        except IntegrityError:
            db_session.rollback()
            rtnval = False
    return rtnval


def renew_lease(
        db_session: DbSession,
        *,
        task_name: str,
        holder_id: str,
        ttl_seconds: float,
        now: Optional[datetime] = None
    ) -> bool:
    """
        Push a held lease's expiry ``ttl_seconds`` into the future.

        :param db_session: The lease bookkeeping session; committed.
        :param task_name: The housekeeping task's name.
        :param holder_id: The identity that should hold the lease.
        :param ttl_seconds: The new time-to-live from ``now``.
        :param now: The current time (defaults to now, UTC).

        :returns: ``False`` when ``holder_id`` no longer holds the lease
                  (it lapsed and another process took it), so the caller
                  must stop working.
    """
    if now is None:
        now = utc_now()
    renewed = db_session.execute(
        update(HousekeepingLease)
        .where(HousekeepingLease.task_name == task_name)
        .where(HousekeepingLease.holder_id == holder_id)
        .values(expires_at=now + timedelta(seconds=ttl_seconds))
        .execution_options(synchronize_session=False)
    )
    db_session.commit()
    rtnval = renewed.rowcount == 1
    return rtnval


def release_lease(
        db_session: DbSession,
        *,
        task_name: str,
        holder_id: str,
        outcome: str,
        now: Optional[datetime] = None
    ) -> None:
    """
        Release a held lease so any process may take it on its next tick,
        and record when the run finished and what it did. Does nothing
        when ``holder_id`` no longer holds the lease.

        :param db_session: The lease bookkeeping session; committed.
        :param task_name: The housekeeping task's name.
        :param holder_id: The identity holding the lease.
        :param outcome: A one-line summary of the run.
        :param now: The current time (defaults to now, UTC).

        :returns: None.
    """
    if now is None:
        now = utc_now()
    db_session.execute(
        update(HousekeepingLease)
        .where(HousekeepingLease.task_name == task_name)
        .where(HousekeepingLease.holder_id == holder_id)
        .values(
            expires_at=now,
            last_finished_at=now,
            last_outcome=outcome[:MAX_OUTCOME_LENGTH],
        )
        .execution_options(synchronize_session=False)
    )
    db_session.commit()
    return
