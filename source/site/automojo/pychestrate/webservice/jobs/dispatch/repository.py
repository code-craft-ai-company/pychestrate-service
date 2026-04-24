"""
.. module:: jobs.dispatch.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for the dispatch-attempt archive.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)


def create_attempt(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        client_id: str,
        pod_id: str,
        envelope_id: str,
        strategy_name: str,
        transport_name: str,
        created_at: datetime
    ) -> DispatchAttempt:
    """
        Insert a fresh ``dispatch_attempt`` row in
        :attr:`DispatchAttemptStatus.PENDING`.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param client_id: Target client UUID.
        :param pod_id: Target pod UUID.
        :param envelope_id: Envelope UUID the attempt carries.
        :param strategy_name: Name of the dispatch strategy that
                              produced the candidate.
        :param transport_name: Transport adapter that will carry
                               the envelope.
        :param created_at: Commit timestamp.

        :returns: The persisted row (flushed, not committed).
    """
    row = DispatchAttempt(
        attempt_id=new_uuid(),
        run_id=run_id,
        project_id=project_id,
        client_id=client_id,
        pod_id=pod_id,
        envelope_id=envelope_id,
        strategy_name=strategy_name,
        transport_name=transport_name,
        status=DispatchAttemptStatus.PENDING,
        created_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def mark_attempt_transmitted(
        *,
        db_session: DbSession,
        attempt: DispatchAttempt,
        transmitted_at: datetime
    ) -> None:
    """
        Transition an attempt row to ``TRANSMITTED`` after the
        transport adapter has accepted the envelope.

        :param db_session: Active SQLAlchemy session.
        :param attempt: Previously-created attempt row.
        :param transmitted_at: Commit timestamp.

        :returns: None.
    """
    attempt.status = DispatchAttemptStatus.TRANSMITTED
    attempt.transmitted_at = transmitted_at
    db_session.flush()
    return


def mark_attempt_transport_failed(
        *,
        db_session: DbSession,
        attempt: DispatchAttempt,
        failure_reason: str
    ) -> None:
    """
        Transition an attempt to ``TRANSPORT_FAILED``, recording
        ``failure_reason`` for operator diagnosis.

        :param db_session: Active SQLAlchemy session.
        :param attempt: Previously-created attempt row.
        :param failure_reason: Short human-readable string.

        :returns: None.
    """
    attempt.status = DispatchAttemptStatus.TRANSPORT_FAILED
    attempt.failure_reason = failure_reason
    db_session.flush()
    return


def mark_attempt_acked(
        *,
        db_session: DbSession,
        attempt: DispatchAttempt,
        acked_at: datetime
    ) -> None:
    """
        Transition an attempt to ``ACKED`` after the client
        returned a receipt for it.

        :param db_session: Active SQLAlchemy session.
        :param attempt: Previously-created attempt row.
        :param acked_at: Commit timestamp.

        :returns: None.
    """
    attempt.status = DispatchAttemptStatus.ACKED
    attempt.acked_at = acked_at
    db_session.flush()
    return


def get_attempt(
        *,
        db_session: DbSession,
        attempt_id: str
    ) -> Optional[DispatchAttempt]:
    """
        Fetch one attempt row by id.

        :param db_session: Active SQLAlchemy session.
        :param attempt_id: Attempt UUID.

        :returns: Row or ``None``.
    """
    rtnval = (
        db_session.query(DispatchAttempt)
        .filter(DispatchAttempt.attempt_id == attempt_id)
        .first()
    )
    return rtnval


def list_attempts_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[DispatchAttempt]:
    """
        Return every attempt row for a run ordered by creation time.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: List of attempts (possibly empty).
    """
    rows = (
        db_session.query(DispatchAttempt)
        .filter(DispatchAttempt.run_id == run_id)
        .order_by(DispatchAttempt.created_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_inflight_attempts(
        *,
        db_session: DbSession
    ) -> List[DispatchAttempt]:
    """
        Return every attempt currently in
        :attr:`DispatchAttemptStatus.TRANSMITTED`. Used at startup
        by the rehydrate hook to rebuild the in-memory
        ``_inflight_by_pod`` gauge (M1 returns the list but does
        not rebuild the gauge — that lands with M2's backoff
        queue).

        :param db_session: Active SQLAlchemy session.

        :returns: List of inflight attempts.
    """
    rows = (
        db_session.query(DispatchAttempt)
        .filter(DispatchAttempt.status == DispatchAttemptStatus.TRANSMITTED)
        .all()
    )
    rtnval = list(rows)
    return rtnval
