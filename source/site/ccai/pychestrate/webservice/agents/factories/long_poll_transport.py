"""
.. module:: agents.factories.long_poll_transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP long-poll client transport — the over-the-wire
               replacement for :class:`InMemoryTransport`.

.. moduleauthor:: Code Craft AI LLC

PR p19g introduces the first real client transport for the
dispatcher. Earlier PRs (5-job-dispatch M1) used the in-process
:class:`InMemoryTransport` reference adapter so the dispatcher
could be exercised without a wire protocol. With the pod-client
agent landing in a sibling repository (PRs S/T/U), the server now
needs to queue signed dispatches for remote agents to fetch + ack
via HTTP.

The shape is intentionally simple — a per-client in-memory
:class:`queue.Queue` keyed by ``client_id``. The dispatcher
enqueues a :class:`DispatchRecord` via :meth:`transmit`; the
long-poll REST handler (``GET /api/v1/clients/{client_id}/
dispatches:next``) pops the next record (or times out and answers
204) via :meth:`await_pending_dispatch`. Persistence is out of
scope for the alpha — server restart drops in-flight dispatches.
The reconciler from PR p19a (``jobs_dispatch_attempt`` watchdog)
is the durability story for now.

The class implements the dispatcher-side
:class:`jobs.dispatch.transport_adapter.ClientTransportProtocol`
(``transport_name`` + ``transmit``). It is *not* the same
``ClientTransportProtocol`` as the Layer-3 factory protocol in
:mod:`agents.factories.transport` — that one models frame
encode/decode for an extension-host transport, which is a separate
concern. PR p19g leaves the factory-protocol version untouched and
adds the long-poll queue as a concrete dispatcher adapter.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import queue
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchTransportError,
)
from ccai.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
)
from ccai.pychestrate.webservice.jobs.envelope import SignedJobEnvelope


#: Transport identifier persisted on every ``jobs_dispatch_attempt``
#: row that travels through the long-poll transport. Stable across
#: releases — downstream tooling filters on this string.
LONG_POLL_TRANSPORT_NAME: str = "http-long-poll"

#: Default ack-deadline for a queued dispatch. The agent has this
#: many seconds from the moment the long-poll handler dequeues the
#: record to POST a matching ``dispatch-ack`` before the reconciler
#: rolls the attempt back to ``PENDING``. Tuned conservatively for
#: alpha; production should drive this off the envelope's
#: ``deadline`` claim.
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


_LOGGER = logging.getLogger("pychestrate.agents.long_poll_transport")


@dataclass(frozen=True)
class DispatchRecord:
    """
        One queued dispatch awaiting agent pickup.

        :param dispatch_attempt_id: UUID of the ``jobs_dispatch_attempt``
                                    row the dispatcher persisted.
        :param run_id: Owning run UUID.
        :param client_id: Target client UUID.
        :param pod_id: Target pod UUID.
        :param envelope_id: Signed envelope UUID.
        :param signed: The :class:`SignedJobEnvelope` itself.
        :param enqueued_at: UTC moment :meth:`LongPollTransport.transmit`
                            queued the record.
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
        Per-client in-memory queue of pending signed dispatches.
        The dispatcher writes; the long-poll HTTP handler reads.

        Thread-safe: the underlying :class:`queue.Queue` instances
        carry their own lock, and the per-client queue lookup is
        guarded by an instance lock so the scheduler thread (PR
        p19a) and the long-poll worker thread can race without
        corrupting the map.

        The dispatcher passes the attempt row's id to
        :meth:`transmit`, and the queued ``PendingDispatch`` carries
        it as ``dispatch_attempt_id`` so the client's ack finds the
        attempt. A caller that passes none (older tests) gets the
        envelope id as a stand-in, which no ack can match.
    """

    def __init__(
            self,
            *,
            ack_deadline_seconds: int = DEFAULT_ACK_DEADLINE_SECONDS
        ) -> None:
        """
            Construct an empty long-poll transport.

            :param ack_deadline_seconds: Seconds the dequeue handler
                                         grants an agent to ack the
                                         dispatched envelope before
                                         the reconciler rolls it back.

            :returns: None.
        """
        self._ack_deadline_seconds: int = ack_deadline_seconds
        self._queues: Dict[str, "queue.Queue[DispatchRecord]"] = {}
        self._lock: threading.Lock = threading.Lock()
        return

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
            Enqueue the signed envelope for ``client_id`` to pull
            on its next long-poll. Returns immediately; the call
            never blocks waiting for the agent. The dispatcher
            treats this as a successful "transmit" and proceeds to
            mark the attempt ``TRANSMITTED``.

            :param client_id: Target client UUID.
            :param pod_id: Target pod UUID.
            :param signed: The :class:`SignedJobEnvelope` to queue.
            :param dispatch_attempt_id: The dispatcher's attempt row id,
                                        handed to the client to ack.

            :returns: None.
            :raises: DispatchTransportError when the client_id is
                     empty or the queue write fails.
        """
        if client_id is None or len(client_id) == 0:
            err_lines = ["LongPollTransport.transmit rejected — empty client_id."]
            err_lines.append("POD_ID: {}".format(pod_id))
            err_msg = "\n".join(err_lines)
            raise DispatchTransportError(err_msg) from None

        now = datetime.now(timezone.utc)
        ack_deadline_at = now + timedelta(seconds=self._ack_deadline_seconds)

        attempt_id_for_client = dispatch_attempt_id
        if attempt_id_for_client is None or len(attempt_id_for_client) == 0:
            attempt_id_for_client = signed.envelope.envelope_id

        record = DispatchRecord(
            dispatch_attempt_id=attempt_id_for_client,
            run_id=signed.envelope.run_id,
            client_id=client_id,
            pod_id=pod_id,
            envelope_id=signed.envelope.envelope_id,
            signed=signed,
            enqueued_at=now,
            ack_deadline_at=ack_deadline_at,
        )

        target_queue = self._queue_for_client(client_id=client_id)
        try:
            target_queue.put(record, block=False)
        except queue.Full as xcpt:
            err_lines = ["LongPollTransport queue full for client."]
            err_lines.append("CLIENT_ID: {}".format(client_id))
            err_lines.append("UNDERLYING: {}".format(str(xcpt)))
            err_msg = "\n".join(err_lines)
            raise DispatchTransportError(err_msg) from xcpt

        _LOGGER.info(
            "long_poll_transport.enqueued client_id=%s run_id=%s envelope_id=%s",
            client_id,
            signed.envelope.run_id,
            signed.envelope.envelope_id,
        )
        return

    def await_pending_dispatch(
            self,
            *,
            client_id: str,
            timeout_seconds: int
        ) -> Optional[DispatchRecord]:
        """
            Block up to ``timeout_seconds`` waiting for a queued
            dispatch for ``client_id``. Returns the next record on
            arrival or ``None`` on timeout.

            The record is dequeued on read — there is no re-delivery.
            The agent ack contract (``POST /runs/{run_id}/
            dispatch-ack``) is the durability seam; missed acks roll
            the attempt back through the reconciler.

            :param client_id: Target client UUID.
            :param timeout_seconds: Seconds to wait. Clamped to
                                    :data:`MAX_LONG_POLL_TIMEOUT_SECONDS`.

            :returns: :class:`DispatchRecord` or ``None`` on timeout.
        """
        effective_timeout = timeout_seconds
        if effective_timeout < 0:
            effective_timeout = 0
        if effective_timeout > MAX_LONG_POLL_TIMEOUT_SECONDS:
            effective_timeout = MAX_LONG_POLL_TIMEOUT_SECONDS

        target_queue = self._queue_for_client(client_id=client_id)
        try:
            record = target_queue.get(
                block=True, timeout=float(effective_timeout),
            )
        except queue.Empty:
            rtnval: Optional[DispatchRecord] = None
            return rtnval

        _LOGGER.info(
            "long_poll_transport.dequeued client_id=%s run_id=%s envelope_id=%s",
            client_id,
            record.run_id,
            record.envelope_id,
        )
        rtnval = record
        return rtnval

    def pending_count(self, *, client_id: str) -> int:
        """
            Return the number of records queued for ``client_id``.
            Approximate (the underlying ``Queue.qsize`` is
            best-effort) — intended for diagnostics, not gating.

            :param client_id: Target client UUID.

            :returns: Best-effort pending-record count.
        """
        with self._lock:
            target_queue = self._queues.get(client_id, None)
        if target_queue is None:
            rtnval = 0
            return rtnval
        rtnval = int(target_queue.qsize())
        return rtnval

    def known_client_ids(self) -> List[str]:
        """
            Return a snapshot of every client UUID this transport
            has ever queued a dispatch for.

            :returns: List of client UUID strings.
        """
        with self._lock:
            rtnval = list(self._queues.keys())
        return rtnval

    def _queue_for_client(self, *, client_id: str) -> "queue.Queue[DispatchRecord]":
        """
            Lazily create the per-client :class:`queue.Queue` and
            return it.

            :param client_id: Target client UUID.

            :returns: The (possibly newly created) queue.
        """
        with self._lock:
            existing = self._queues.get(client_id, None)
            if existing is not None:
                rtnval = existing
                return rtnval
            created: "queue.Queue[DispatchRecord]" = queue.Queue()
            self._queues[client_id] = created
            rtnval = created
        return rtnval


__all__ = [
    "DEFAULT_ACK_DEADLINE_SECONDS",
    "DEFAULT_LONG_POLL_TIMEOUT_SECONDS",
    "DispatchRecord",
    "LONG_POLL_TRANSPORT_NAME",
    "LongPollTransport",
    "MAX_LONG_POLL_TIMEOUT_SECONDS",
]
