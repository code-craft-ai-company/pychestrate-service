"""
.. module:: jobs.dispatch.transport_adapter
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Transport protocol + in-memory reference impl.

.. moduleauthor:: Automation Mojo LLC

The dispatcher hands a :class:`SignedJobEnvelope` to whatever
transport the target client is reachable on. The real transports
(HTTP/2, WebSocket, gRPC, mTLS tunnel) land with
``3-client-agent-protocol`` M2; M1 ships a protocol contract plus an
:class:`InMemoryTransport` reference impl that records every call so
tests can assert on transmitted envelopes without standing up a
real transport.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from dataclasses import dataclass
from typing import List, Optional

from automojo.pychestrate.webservice.jobs.envelope import SignedJobEnvelope


IN_MEMORY_TRANSPORT_NAME: str = "in-memory"


@dataclass(frozen=True)
class TransportCall:
    """
        One recorded :meth:`ClientTransportProtocol.transmit` call.
        Tests assert on the recorded list rather than mocking the
        transport.

        :param client_id: Target client UUID.
        :param pod_id: Target pod UUID.
        :param envelope_id: Transmitted envelope id.
        :param signed: The signed envelope handed to the transport.
    """
    client_id: str
    pod_id: str
    envelope_id: str
    signed: SignedJobEnvelope


class ClientTransportProtocol:
    """
        Contract for transport adapters the dispatcher talks to.
        Real implementations live outside this package (HTTP/2,
        WebSocket, …); the dispatcher only holds a reference to one
        object that honors this protocol.
    """

    def transport_name(self) -> str:
        """
            Stable identifier recorded on the attempt row.

            :returns: Short transport identifier.
        """
        raise NotImplementedError("Subclasses must implement transport_name")

    def transmit(
            self,
            *,
            client_id: str,
            pod_id: str,
            signed: SignedJobEnvelope
        ) -> None:
        """
            Hand the signed envelope to the target client. MUST
            raise :class:`DispatchTransportError` on any failure
            the dispatcher should record against the attempt row.

            :param client_id: Target client UUID.
            :param pod_id: Target pod UUID.
            :param signed: The :class:`SignedJobEnvelope` to send.

            :returns: None.
            :raises: DispatchTransportError on transport failure.
        """
        raise NotImplementedError("Subclasses must implement transmit")


class InMemoryTransport(ClientTransportProtocol):
    """
        Reference transport for tests. Stores every call in an
        in-process list and returns without side effects. Supports
        opt-in failure injection via :meth:`configure_failure`.
    """

    def __init__(self) -> None:
        """
            Construct an empty in-memory transport.

            :returns: None.
        """
        self._calls: List[TransportCall] = []
        self._lock: threading.Lock = threading.Lock()
        self._next_failure_reason: Optional[str] = None
        return

    def transport_name(self) -> str:
        rtnval = IN_MEMORY_TRANSPORT_NAME
        return rtnval

    def configure_failure(self, *, reason: Optional[str]) -> None:
        """
            Arm the next :meth:`transmit` call to raise
            :class:`DispatchTransportError`. Set ``reason`` to
            ``None`` to clear.

            :param reason: Failure reason string, or ``None`` to
                           disarm.

            :returns: None.
        """
        with self._lock:
            self._next_failure_reason = reason
        return

    def transmit(
            self,
            *,
            client_id: str,
            pod_id: str,
            signed: SignedJobEnvelope
        ) -> None:
        from automojo.pychestrate.webservice.jobs.dispatch.errors import (
            DispatchTransportError,
        )
        with self._lock:
            pending_failure = self._next_failure_reason
            self._next_failure_reason = None

        if pending_failure is not None:
            raise DispatchTransportError(pending_failure) from None

        call = TransportCall(
            client_id=client_id,
            pod_id=pod_id,
            envelope_id=signed.envelope.envelope_id,
            signed=signed,
        )
        with self._lock:
            self._calls.append(call)
        return

    def calls(self) -> List[TransportCall]:
        """
            Return a snapshot of every recorded transmit call.

            :returns: List of :class:`TransportCall` entries in
                      transmission order.
        """
        with self._lock:
            rtnval = list(self._calls)
        return rtnval

    def reset(self) -> None:
        """
            Clear the recorded-call list and any armed failure.

            :returns: None.
        """
        with self._lock:
            self._calls = []
            self._next_failure_reason = None
        return
