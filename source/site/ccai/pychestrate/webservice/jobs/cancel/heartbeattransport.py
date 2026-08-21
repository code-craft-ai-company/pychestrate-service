"""
.. module:: jobs.cancel.heartbeattransport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HeartbeatCancelTransport — the production pull-based
               cancel transport drained by the pod-client heartbeat.

.. moduleauthor:: Code Craft AI LLC

The :class:`jobs.cancel.dispatcher.CancelTransportProtocol` contract
was written for a push channel: ``send_cancel`` hands the request to
the pod and raises :class:`CancelTransportError` when the wire is
down. The pod client has no inbound channel — nginx terminates mTLS
in front of the service and the pod never listens — so every
client-bound signal in this system is PULLED by the pod: the job
envelope through ``GET /clients/{client_id}/dispatches:next`` and
liveness through ``GET /clients/{client_id}/heartbeat``.

This transport therefore delivers by PERSISTING rather than by
writing to a socket. The ``jobs_cancel_request`` row the dispatcher
inserted before calling ``send_cancel`` IS the queue; the
client-heartbeat handler drains it with
:func:`jobs.cancel.repository.list_open_for_client`. That has three
consequences worth stating plainly:

* ``send_cancel`` cannot fail, so the dispatcher's FAILED branch is
  never taken through this transport. Nothing is lost by that — a
  service restart does not drop a queued cancel the way an in-memory
  mailbox would, and a second service instance serves the same queue.
* The row stays open until the pod acknowledges it, so an unanswered
  cancel is re-delivered on every heartbeat. Delivery is at-least-
  once and the pod-side handler is idempotent, which is the correct
  trade for a channel whose response can be dropped.
* ``CancelStatus.TRANSMITTED`` means "queued for the pod to pull",
  not "handed to the pod". ``CancelStatus.ACKED`` is the only status
  that means the pod saw it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.jobs.cancel import repository
from ccai.pychestrate.webservice.jobs.cancel.dispatcher import (
    CancelTransportProtocol,
)
from ccai.pychestrate.webservice.jobs.cancel.events import (
    CancelEventTopics,
)
from ccai.pychestrate.webservice.jobs.cancel.models import (
    CancelRequest,
    CancelStatus,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    repository as run_repo,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import TERMINAL_STATES
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


#: ``transport_name`` reported by this transport. Mirrors the
#: ``LONG_POLL_TRANSPORT_NAME`` convention used by the dispatch
#: pull channel so operator logs name the same delivery mechanism
#: on both halves of the client protocol.
HEARTBEAT_CANCEL_TRANSPORT_NAME: str = "client-heartbeat-cancel"


_LOGGER = logging.getLogger("pychestrate.jobs.cancel.heartbeattransport")


class HeartbeatCancelTransport(CancelTransportProtocol):
    """
        Pull-based cancel transport. ``send_cancel`` records that the
        request is queued for the pod to collect on its next
        heartbeat; the pod-client heartbeat handler performs the
        actual delivery.
    """

    def __init__(self) -> None:
        """
            Initializes a :class:`HeartbeatCancelTransport`.
        """
        return

    def transport_name(self) -> str:
        """
            Gets the transport's operator-facing name.

            :returns: The transport name string.
        """
        rtnval = HEARTBEAT_CANCEL_TRANSPORT_NAME
        return rtnval

    def send_cancel(
            self,
            *,
            run_id: str,
            client_id: str,
            request_id: str,
            reason: str
        ) -> None:
        """
            Queue the cancel for pull delivery.

            The dispatcher has already inserted the
            :class:`CancelRequest` row and will flip it to
            ``TRANSMITTED`` when this call returns without raising.
            That row is the queue, so there is nothing further to
            transmit here — this method records the intent for
            operator triage and returns.

            :param run_id: Run UUID being cancelled.
            :param client_id: Target client UUID.
            :param request_id: Cancel-request UUID.
            :param reason: Operator-supplied cancel reason.

            :returns: None.
        """
        _LOGGER.info(
            "pychestrate.jobs.cancel.queued_for_pull request_id=%s"
            " run_id=%s client_id=%s reason=%s",
            request_id,
            run_id,
            client_id,
            reason,
        )
        return


def cancellation_to_dict(*, row: CancelRequest) -> Dict[str, Any]:
    """
        Serialize one open cancel request to the OpenAPI
        ``PendingCancellation`` schema the heartbeat response
        carries.

        :param row: An open :class:`CancelRequest`.

        :returns: JSON-friendly dict.
    """
    requested_at = row.requested_at
    requested_at_text = ""
    if requested_at is not None:
        requested_at_text = requested_at.isoformat()

    reason_text = row.reason
    if reason_text is None:
        reason_text = ""

    rtnval: Dict[str, Any] = {
        "request_id": str(row.request_id),
        "run_id": str(row.run_id),
        "project_id": str(row.project_id),
        "client_id": str(row.client_id),
        "reason": reason_text,
        "requested_at": requested_at_text,
        "transport_name": HEARTBEAT_CANCEL_TRANSPORT_NAME,
    }
    return rtnval


def _run_is_terminal(*, db_session: DbSession, run_id: str) -> bool:
    """
        Report whether the run-state row for ``run_id`` has already
        reached a terminal state.

        A run with no state row is NOT treated as terminal — the
        cancel still gets delivered, and the pod-side handler is a
        no-op for a run it does not recognize. Refusing to deliver on
        a missing row would silently drop cancels for any run whose
        state bookkeeping lags.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: True when the run row exists and is terminal.
    """
    row = run_repo.find_run(db_session=db_session, run_id=run_id)
    if row is None:
        rtnval = False
        return rtnval

    rtnval = row.state in TERMINAL_STATES
    return rtnval


def drain_pending_cancellations(
        *,
        db_session: DbSession,
        client_id: str
    ) -> List[Dict[str, Any]]:
    """
        Collect the open cancel requests targeting ``client_id`` and
        render them for the heartbeat response body.

        Rows are NOT closed here. A cancel stays open until the pod
        acknowledges it through
        :func:`acknowledge_client_cancellation`, so a heartbeat
        response the pod never received is retried on the next
        heartbeat rather than lost.

        Two things stop that retry from becoming a permanent loop.
        The pod closes the row by reporting a terminal outcome for
        the run, and a request whose run already reached a terminal
        state is filtered out here — that covers the case where the
        cancel raced a run that was finishing anyway, so the pod
        never had a job to stop and never posts a cancelled result.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Calling client's UUID.

        :returns: List of ``PendingCancellation`` dicts (possibly
                  empty).
    """
    rows = repository.list_open_for_client(
        db_session=db_session, client_id=client_id,
    )

    rtnval: List[Dict[str, Any]] = []
    for row in rows:
        run_id = str(row.run_id)
        already_terminal = _run_is_terminal(
            db_session=db_session, run_id=run_id,
        )
        if already_terminal is True:
            _LOGGER.info(
                "pychestrate.jobs.cancel.drain_skipped_terminal"
                " request_id=%s run_id=%s client_id=%s",
                str(row.request_id),
                run_id,
                client_id,
            )
            continue

        entry = cancellation_to_dict(row=row)
        rtnval.append(entry)

    return rtnval


def acknowledge_client_cancellation(
        *,
        db_session: DbSession,
        run_id: str,
        client_id: str,
        acked_at: Optional[Any] = None
    ) -> Optional[CancelRequest]:
    """
        Close the open cancel request for ``(run_id, client_id)``
        because the pod confirmed it received the signal.

        Unlike :func:`jobs.cancel.dispatcher.handle_ack` — which is
        keyed by ``request_id`` and raises when the row is missing or
        in the wrong status — this helper is keyed by the pair the
        pod actually knows and is a NO-OP when there is nothing open
        to close. A pod acking a cancel twice, or acking a run whose
        cancel was already reconciled away, must not be answered with
        an error: it did the right thing and the duplicate is a
        consequence of at-least-once delivery.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID the pod cancelled.
        :param client_id: Acknowledging client's UUID.
        :param acked_at: Optional ack timestamp; defaults to now.

        :returns: The closed :class:`CancelRequest`, or ``None`` when
                  no open request matched.
        :raises: CancelError
    """
    row = repository.find_open_for_run_and_client(
        db_session=db_session, run_id=run_id, client_id=client_id,
    )
    if row is None:
        _LOGGER.info(
            "pychestrate.jobs.cancel.ack_noop run_id=%s client_id=%s",
            run_id,
            client_id,
        )
        rtnval = None
        return rtnval

    when = acked_at
    if when is None:
        when = utc_now()

    row.status = CancelStatus.ACKED
    row.acked_at = when
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=CancelEventTopics.ACK_RECEIVED,
            payload={
                "request_id": str(row.request_id),
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "client_id": str(row.client_id),
                "acked_at": when.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    _LOGGER.info(
        "pychestrate.jobs.cancel.acked request_id=%s run_id=%s client_id=%s",
        str(row.request_id),
        run_id,
        client_id,
    )

    rtnval = row
    return rtnval


__all__ = [
    "HEARTBEAT_CANCEL_TRANSPORT_NAME",
    "HeartbeatCancelTransport",
    "acknowledge_client_cancellation",
    "cancellation_to_dict",
    "drain_pending_cancellations",
]
