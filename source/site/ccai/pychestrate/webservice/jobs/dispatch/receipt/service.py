"""
.. module:: jobs.dispatch.receipt.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: DispatchReceiptService — record + lookup facade.

.. moduleauthor:: Code Craft AI LLC

The service layer validates every M1 invariant before writing:

* ``(client_id, client_local_run_id)`` is unique — re-posting the
  same receipt is idempotent and returns the originally-persisted
  row.
* A second distinct receipt for the same ``run_id`` raises
  :class:`DuplicateRunReceiptError`.
* The receipt's ``envelope_id`` MUST match an existing attempt on
  the same ``run_id`` (M2 tightens this to also match the attempt
  referenced by ``attempt_id``; M1 accepts any attempt row whose
  envelope id agrees).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.jobs.dispatch.receipt import repository
from ccai.pychestrate.webservice.jobs.dispatch.receipt.errors import (
    DuplicateRunReceiptError,
    ReceiptEnvelopeMismatchError,
    ReceiptNotFoundError,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt.models import (
    DispatchReceipt,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt.schema import (
    ReceiptRecord,
)
from ccai.pychestrate.webservice.jobs.dispatch import repository as dispatch_repo
from ccai.pychestrate.webservice.jobs.dispatch.models import DispatchAttempt


def record(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        client_id: str,
        attempt_id: str,
        envelope_id: str,
        client_local_run_id: str,
        received_at: Optional[datetime] = None,
        deadline_at: Optional[datetime] = None,
        launch_pid: Optional[int] = None
    ) -> ReceiptRecord:
    """
        Persist a receipt (or return the previously-persisted one
        on retry). Computes ``late_arrival = received_at > deadline_at``
        inline so downstream metrics / run-state consumers can key
        on the boolean.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Owning run UUID.
        :param project_id: Owning project UUID.
        :param client_id: Client UUID.
        :param attempt_id: Linked ``dispatch_attempt`` UUID.
        :param envelope_id: Envelope the receipt acknowledges.
        :param client_local_run_id: Client-assigned local id —
                                    unique per ``client_id``.
        :param received_at: Observed timestamp. Defaults to
                            ``utc_now()``.
        :param deadline_at: Expected-by timestamp. Optional.
        :param launch_pid: Client process id. Optional.

        :returns: :class:`ReceiptRecord`.
        :raises: DuplicateRunReceiptError when a second distinct
                 receipt arrives for the same ``run_id``;
                 ReceiptEnvelopeMismatchError when ``envelope_id``
                 does not match any attempt of the run.
    """
    effective_received_at = received_at
    if effective_received_at is None:
        effective_received_at = utc_now()

    existing_by_local = repository.find_by_local_key(
        db_session=db_session,
        client_id=client_id,
        client_local_run_id=client_local_run_id,
    )
    if existing_by_local is not None:
        rtnval = _to_record(row=existing_by_local)
        return rtnval

    existing_for_run = repository.find_by_run(db_session=db_session, run_id=run_id)
    if existing_for_run is not None:
        if existing_for_run.client_local_run_id != client_local_run_id:
            err_lines = ["Duplicate receipt for run with distinct client_local_run_id."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("EXISTING_LOCAL: {}".format(existing_for_run.client_local_run_id))
            err_lines.append("NEW_LOCAL: {}".format(client_local_run_id))
            err_msg = os.linesep.join(err_lines)
            raise DuplicateRunReceiptError(err_msg) from None

    _assert_envelope_matches_attempt(
        db_session=db_session,
        run_id=run_id,
        envelope_id=envelope_id,
    )

    late_arrival = False
    if deadline_at is not None:
        late_arrival = effective_received_at > deadline_at

    row = repository.insert_receipt(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        client_id=client_id,
        attempt_id=attempt_id,
        envelope_id=envelope_id,
        client_local_run_id=client_local_run_id,
        received_at=effective_received_at,
        deadline_at=deadline_at,
        late_arrival=late_arrival,
        launch_pid=launch_pid,
    )
    db_session.commit()

    rtnval = _to_record(row=row)
    return rtnval


def lookup_by_local(
        *,
        db_session: DbSession,
        client_id: str,
        client_local_run_id: str,
        strict: bool = False
    ) -> Optional[ReceiptRecord]:
    """
        Return the receipt bound to a client's local run id, or
        ``None`` when not found. When ``strict=True`` raises
        :class:`ReceiptNotFoundError` instead of returning ``None``.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Client UUID.
        :param client_local_run_id: Client-assigned local id.
        :param strict: Raise on miss instead of returning ``None``.

        :returns: :class:`ReceiptRecord` or ``None``.
        :raises: ReceiptNotFoundError (strict only).
    """
    row = repository.find_by_local_key(
        db_session=db_session,
        client_id=client_id,
        client_local_run_id=client_local_run_id,
    )
    if row is None:
        if strict is True:
            err_lines = ["Receipt not found by client-local key."]
            err_lines.append("CLIENT_ID: {}".format(client_id))
            err_lines.append("CLIENT_LOCAL_RUN_ID: {}".format(client_local_run_id))
            err_msg = os.linesep.join(err_lines)
            raise ReceiptNotFoundError(err_msg) from None
        return None
    rtnval = _to_record(row=row)
    return rtnval


def lookup_by_run(
        *,
        db_session: DbSession,
        run_id: str,
        strict: bool = False
    ) -> Optional[ReceiptRecord]:
    """
        Return the receipt bound to a run id, or ``None`` when no
        receipt has landed yet. ``strict=True`` raises on miss.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param strict: Raise on miss instead of returning ``None``.

        :returns: :class:`ReceiptRecord` or ``None``.
        :raises: ReceiptNotFoundError (strict only).
    """
    row = repository.find_by_run(db_session=db_session, run_id=run_id)
    if row is None:
        if strict is True:
            err_lines = ["Receipt not found by run id."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_msg = os.linesep.join(err_lines)
            raise ReceiptNotFoundError(err_msg) from None
        return None
    rtnval = _to_record(row=row)
    return rtnval


def _assert_envelope_matches_attempt(
        *,
        db_session: DbSession,
        run_id: str,
        envelope_id: str
    ) -> None:
    """
        Verify that the receipt's ``envelope_id`` matches at least
        one ``dispatch_attempt`` on the run. A mismatched
        ``envelope_id`` means the receipt belongs to a different
        run and would silently corrupt downstream routing.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param envelope_id: Envelope UUID on the receipt.

        :returns: None.
        :raises: ReceiptEnvelopeMismatchError when no attempt
                 matches.
    """
    attempts = dispatch_repo.list_attempts_for_run(
        db_session=db_session, run_id=run_id,
    )
    matched = False
    for attempt in attempts:
        if str(attempt.envelope_id) == envelope_id:
            matched = True
            break
    if matched is False:
        err_lines = ["Receipt envelope_id does not match any attempt for the run."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("ENVELOPE_ID: {}".format(envelope_id))
        err_lines.append("ATTEMPT_COUNT: {}".format(len(attempts)))
        err_msg = os.linesep.join(err_lines)
        raise ReceiptEnvelopeMismatchError(err_msg) from None
    return


def _to_record(*, row: DispatchReceipt) -> ReceiptRecord:
    """
        Convert a persisted row into the caller-facing read-model.

        :param row: ORM row.

        :returns: :class:`ReceiptRecord`.
    """
    rtnval = ReceiptRecord(
        receipt_id=str(row.receipt_id),
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        client_id=str(row.client_id),
        attempt_id=str(row.attempt_id),
        envelope_id=str(row.envelope_id),
        client_local_run_id=row.client_local_run_id,
        received_at=row.received_at,
        deadline_at=row.deadline_at,
        late_arrival=bool(row.late_arrival),
        launch_pid=row.launch_pid,
    )
    return rtnval
