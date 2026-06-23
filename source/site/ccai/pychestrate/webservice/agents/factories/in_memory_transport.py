"""
.. module:: agents.factories.in_memory_transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference InMemoryLoopbackTransport for tests.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import ClassVar

from ccai.pychestrate.webservice.agents.factories.transport import (
    ClientTransportProtocol,
    InboundFrame,
    OutboundFrame,
)


class InMemoryLoopbackTransport(ClientTransportProtocol):
    """
        JSON-over-bytes loopback used by tests and the extension host
        until the real WebSocket+mTLS transport lands.
    """

    factory_protocol_name: ClassVar[str] = "client_transport"
    transport_name: ClassVar[str] = "in_memory_loopback"
    PRECEDENCE: ClassVar[int] = 50

    @classmethod
    def encode(cls, *, frame: OutboundFrame) -> bytes:
        body = {"kind": frame.kind, "payload": dict(frame.payload or {})}
        rtnval = json.dumps(body, sort_keys=True).encode("utf-8")
        return rtnval

    @classmethod
    def decode(cls, *, payload: bytes) -> InboundFrame:
        body = json.loads(payload.decode("utf-8"))
        rtnval = InboundFrame(
            kind=str(body.get("kind", "")),
            payload=dict(body.get("payload", {}) or {}),
        )
        return rtnval
