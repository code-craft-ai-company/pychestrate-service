"""
.. module:: agents.factories.long_poll_transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP long-poll client transport — the over-the-wire
               replacement for :class:`InMemoryTransport`.

.. moduleauthor:: Code Craft AI LLC

Pods fetch their signed dispatches over HTTP: the long-poll REST
handler (``GET /api/v1/clients/{client_id}/dispatches:next``) waits
for the next dispatch addressed to the calling client, and the pod acks
it with ``POST /runs/{run_id}/dispatch-ack``.

The queue is the database. The dispatcher persists the signed envelope
(``jobs_envelope_archive``) and a ``jobs_dispatch_attempt`` row, then
calls :meth:`LongPollTransport.transmit`, which only validates the
target -- it keeps nothing in memory. The handler claims the oldest
TRANSMITTED attempt for the client with :func:`await_next_dispatch`.
Earlier versions kept a per-client ``queue.Queue`` in the process that
ran the dispatcher, which only worked with one worker: under gunicorn's
four workers the pod's poll landed on a worker that had never seen the
job, and the run sat in "dispatched" (E2E-17). Any worker can now
serve any pod, and a service restart no longer drops queued jobs.

A claim stamps ``delivered_at`` with a conditional UPDATE, so one poll
gets each attempt. An attempt that was delivered but not acked within
:data:`DEFAULT_ACK_DEADLINE_SECONDS` can be claimed again, so a pod
that died between receiving and acking gets the job re-delivered
(E2E-16); the ack moves the attempt to ACKED and ends that.

The class implements the dispatcher-side
:class:`jobs.dispatch.transport_adapter.ClientTransportProtocol`
(``transport_name`` + ``transmit``). It is *not* the same
``ClientTransportProtocol`` as the Layer-3 factory protocol in
:mod:`agents.factories.transport` — that one models frame
encode/decode for an extension-host transport, which is a separate
concern.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import time
import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import or_

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchTransportError,
)
from ccai.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)
from ccai.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    SignedJobEnvelope,
    get_envelope,
    parse,
)


#: Transport identifier persisted on every ``jobs_dispatch_attempt``
#: row that travels through the long-poll transport. Stable across
#: releases — downstream tooling filters on this string.
LONG_POLL_TRANSPORT_NAME: str = "http-long-poll"

#: Seconds a pod has, from the moment its long-poll claims a dispatch,
#: to POST the matching ``dispatch-ack``. An attempt still unacked after
#: this is claimable again, so the job is re-delivered.
DEFAULT_ACK_DEADLINE_SECONDS: int = 60

#: Hard cap on the long-poll wait the REST handler will honor. Set
#: well below typical proxy / gunicorn timeout windows so we never
#: race the upstream socket close.
MAX_LONG_POLL_TIMEOUT_SECONDS: int = 60

#: Default long-poll wait when the handler does not pass an
#: explicit timeout. Matches the OpenAPI ``timeout_seconds`` query
#: param default so client + server agree on the expected blocking
#: window.
DEFAULT_LONG_POLL_TIMEOUT_SECONDS: int = 30

#: How often a waiting long-poll looks for a newly transmitted attempt.
DEFAULT_DELIVERY_POLL_INTERVAL_SECONDS: float = 1.0

#: How many candidate attempts one claim pass considers.
CLAIM_CANDIDATE_LIMIT: int = 10


_LOGGER = logging.getLogger("pychestrate.agents.long_poll_transport")


@dataclass(frozen=True)
class DispatchRecord:
    """
        One dispatch handed to a pod's long-poll.

        :param dispatch_attempt_id: UUID of the ``jobs_dispatch_attempt``
                                    row the dispatcher persisted.
        :param run_id: Owning run UUID.
        :param client_id: Target client UUID.
        :param pod_id: Target pod UUID.
        :param envelope_id: Signed envelope UUID.
        :param signed: The :class:`SignedJobEnvelope` itself.
        :param enqueued_at: UTC moment the dispatcher transmitted the
                            attempt.
        :param ack_deadline_at: UTC deadline for the agent to POST
                                its dispatch-ack before the reconciler
                                marks the attempt lost.
    """
    dispatch_attempt_id: str
    run_id: str
    client_id: str
    pod_id: str
    envelope_id: str
    signed: SignedJobEnvelope
    enqueued_at: datetime
    ack_deadline_at: datetime


class LongPollTransport(ClientTransportProtocol):
    """
        Dispatcher-side adapter for pods that long-poll over HTTP. The
        attempt row and archived envelope the dispatcher writes before
        :meth:`transmit` are the queue; :func:`await_next_dispatch`
        delivers from them.
    """

    def __init__(
            self,
            *,
            ack_deadline_seconds: int = DEFAULT_ACK_DEADLINE_SECONDS
        ) -> None:
        """
            :param ack_deadline_seconds: Seconds a pod has to ack a
                                         claimed dispatch before it is
                                         re-delivered.

            :returns: None.
        """
        self._ack_deadline_seconds: int = ack_deadline_seconds
        return

    @property
    def ack_deadline_seconds(self) -> int:
        return self._ack_deadline_seconds

    def transport_name(self) -> str:
        """
            Stable transport identifier recorded on the attempt row.

            :returns: ``"http-long-poll"``.
        """
        rtnval = LONG_POLL_TRANSPORT_NAME
        return rtnval

    def transmit(
            self,
            *,
            client_id: str,
            pod_id: str,
            signed: SignedJobEnvelope,
            dispatch_attempt_id: Optional[str] = None
        ) -> None:
        """
            Accept a dispatch for ``client_id``. Nothing is held in
            memory: the dispatcher has already persisted the attempt
            row and the signed envelope, and marks the attempt
            TRANSMITTED when this returns, which makes it claimable by
            the client's next long-poll on any worker.

            :param client_id: Target client UUID.
            :param pod_id: Target pod UUID.
            :param signed: The :class:`SignedJobEnvelope` being sent.
            :param dispatch_attempt_id: The attempt row's id (logged).

            :returns: None.
            :raises: DispatchTransportError when the client_id is empty.
        """
        if client_id is None or len(client_id) == 0:
            err_lines = ["LongPollTransport.transmit rejected — empty client_id."]
            err_lines.append("POD_ID: {}".format(pod_id))
            err_msg = "\n".join(err_lines)
            raise DispatchTransportError(err_msg) from None

        _LOGGER.info(
            "long_poll_transport.transmitted client_id=%s run_id=%s envelope_id=%s attempt_id=%s",
            client_id,
            signed.envelope.run_id,
            signed.envelope.envelope_id,
            dispatch_attempt_id,
        )
        return


def _record_from_rows(
        *,
        attempt: DispatchAttempt,
        envelope_row: Any,
        claimed_at: datetime,
        ack_deadline_seconds: int
    ) -> DispatchRecord:
    """
        Rebuild the :class:`DispatchRecord` a pod receives from the
        attempt row and the archived signed envelope.
    """
    canonical_payload = bytes(envelope_row.canonical_payload)
    signed = SignedJobEnvelope(
        envelope=parse(canonical_payload=canonical_payload),
        canonical_payload=canonical_payload,
        signature=bytes(envelope_row.signature),
        key_id=str(envelope_row.key_id),
        signed_at=envelope_row.issued_at,
    )
    enqueued_at = attempt.transmitted_at
    if enqueued_at is None:
        enqueued_at = attempt.created_at
    rtnval = DispatchRecord(
        dispatch_attempt_id=str(attempt.attempt_id),
        run_id=str(attempt.run_id),
        client_id=str(attempt.client_id),
        pod_id=str(attempt.pod_id),
        envelope_id=str(attempt.envelope_id),
        signed=signed,
        enqueued_at=enqueued_at,
        ack_deadline_at=claimed_at + timedelta(seconds=ack_deadline_seconds),
    )
    return rtnval


def claim_next_dispatch(
        *,
        db_session: Any,
        client_id: str,
        ack_deadline_seconds: int = DEFAULT_ACK_DEADLINE_SECONDS,
        now: Optional[datetime] = None
    ) -> Optional[DispatchRecord]:
    """
        Claim the oldest dispatch waiting for ``client_id``: a
        TRANSMITTED attempt never delivered, or delivered more than
        ``ack_deadline_seconds`` ago without an ack. The claim is a
        conditional UPDATE of ``delivered_at``, so two workers polling
        for the same client never both get it. Commits a successful
        claim; ends the transaction either way, so a waiting poll holds
        no database lock.

        :param db_session: Active SQLAlchemy session.
        :param client_id: The polling client's UUID.
        :param ack_deadline_seconds: Re-delivery window for unacked claims.
        :param now: Evaluation time (tests); defaults to now.

        :returns: The claimed :class:`DispatchRecord`, or ``None``.
    """
    claimed_at = now if now is not None else utc_now()
    redeliver_before = claimed_at - timedelta(seconds=ack_deadline_seconds)
    try:
        client_uuid = uuid.UUID(str(client_id))
    except ValueError:
        rtnval: Optional[DispatchRecord] = None
        return rtnval

    candidates = (
        db_session.query(DispatchAttempt)
        .filter(DispatchAttempt.client_id == client_uuid)
        .filter(DispatchAttempt.status == DispatchAttemptStatus.TRANSMITTED)
        .filter(or_(
            DispatchAttempt.delivered_at.is_(None),
            DispatchAttempt.delivered_at < redeliver_before,
        ))
        .order_by(DispatchAttempt.created_at.asc())
        .limit(CLAIM_CANDIDATE_LIMIT)
        .all()
    )
    candidate_keys = [(row.attempt_id, row.delivered_at) for row in candidates]
    db_session.rollback()

    for attempt_id, previous_delivered_at in candidate_keys:
        claim = (
            db_session.query(DispatchAttempt)
            .filter(DispatchAttempt.attempt_id == attempt_id)
            .filter(DispatchAttempt.status == DispatchAttemptStatus.TRANSMITTED)
        )
        if previous_delivered_at is None:
            claim = claim.filter(DispatchAttempt.delivered_at.is_(None))
        else:
            claim = claim.filter(DispatchAttempt.delivered_at == previous_delivered_at)
        claimed_rows = claim.update(
            {DispatchAttempt.delivered_at: claimed_at}, synchronize_session=False,
        )
        if claimed_rows != 1:
            db_session.rollback()
            continue

        attempt = db_session.query(DispatchAttempt).filter(
            DispatchAttempt.attempt_id == attempt_id).one()
        envelope_row = get_envelope(db_session=db_session, envelope_id=str(attempt.envelope_id))
        if envelope_row is None:
            _LOGGER.error(
                "long_poll_transport.envelope_missing attempt_id=%s envelope_id=%s",
                attempt_id, attempt.envelope_id,
            )
            db_session.rollback()
            continue

        record = _record_from_rows(
            attempt=attempt, envelope_row=envelope_row,
            claimed_at=claimed_at, ack_deadline_seconds=ack_deadline_seconds,
        )
        db_session.commit()
        _LOGGER.info(
            "long_poll_transport.claimed client_id=%s run_id=%s attempt_id=%s redelivery=%s",
            client_id, record.run_id, record.dispatch_attempt_id,
            previous_delivered_at is not None,
        )
        rtnval = record
        return rtnval

    rtnval = None
    return rtnval


def await_next_dispatch(
        *,
        db_session: Any,
        client_id: str,
        timeout_seconds: int,
        ack_deadline_seconds: int = DEFAULT_ACK_DEADLINE_SECONDS,
        poll_interval_seconds: float = DEFAULT_DELIVERY_POLL_INTERVAL_SECONDS,
        sleep_func: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic
    ) -> Optional[DispatchRecord]:
    """
        Wait up to ``timeout_seconds`` for a dispatch to claim for
        ``client_id``, checking every ``poll_interval_seconds``.

        :param db_session: Active SQLAlchemy session.
        :param client_id: The polling client's UUID.
        :param timeout_seconds: Seconds to wait; clamped to
                                0..:data:`MAX_LONG_POLL_TIMEOUT_SECONDS`.
        :param ack_deadline_seconds: Re-delivery window for unacked claims.
        :param poll_interval_seconds: Seconds between claim attempts.
        :param sleep_func: Sleep override (tests).
        :param clock: Monotonic clock override (tests).

        :returns: The claimed :class:`DispatchRecord`, or ``None`` on timeout.
    """
    effective_timeout = timeout_seconds
    if effective_timeout < 0:
        effective_timeout = 0
    if effective_timeout > MAX_LONG_POLL_TIMEOUT_SECONDS:
        effective_timeout = MAX_LONG_POLL_TIMEOUT_SECONDS
    give_up_at = clock() + float(effective_timeout)

    while True:
        record = claim_next_dispatch(
            db_session=db_session, client_id=client_id,
            ack_deadline_seconds=ack_deadline_seconds,
        )
        if record is not None:
            rtnval: Optional[DispatchRecord] = record
            return rtnval
        remaining = give_up_at - clock()
        if remaining <= 0:
            rtnval = None
            return rtnval
        sleep_func(min(poll_interval_seconds, remaining))


__all__ = [
    "CLAIM_CANDIDATE_LIMIT",
    "DEFAULT_ACK_DEADLINE_SECONDS",
    "DEFAULT_DELIVERY_POLL_INTERVAL_SECONDS",
    "DEFAULT_LONG_POLL_TIMEOUT_SECONDS",
    "DispatchRecord",
    "LONG_POLL_TRANSPORT_NAME",
    "LongPollTransport",
    "MAX_LONG_POLL_TIMEOUT_SECONDS",
    "await_next_dispatch",
    "claim_next_dispatch",
]
