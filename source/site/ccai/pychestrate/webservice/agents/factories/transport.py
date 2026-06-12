"""
.. module:: agents.factories.transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``client_transport`` factory protocol base.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class InboundFrame:
    """
        Decoded inbound frame from a client.

        :param kind: Frame kind string (``heartbeat``, ``enroll``, ...).
        :param payload: Opaque mapping.
    """
    kind: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class OutboundFrame:
    """
        Encoded outbound frame to a client.

        :param kind: Frame kind string.
        :param payload: Opaque mapping.
    """
    kind: str
    payload: Mapping[str, Any]


class ClientTransportProtocol(FactoryProtocolBase):
    """
        Contract implemented by client agent transports.
    """

    factory_protocol_name: ClassVar[str] = "client_transport"
    protocol_schema_version: ClassVar[int] = 1
    transport_name: ClassVar[str] = ""

    @classmethod
    def encode(cls, *, frame: OutboundFrame) -> bytes:
        raise NotImplementedError("Subclasses must implement encode()")

    @classmethod
    def decode(cls, *, payload: bytes) -> InboundFrame:
        raise NotImplementedError("Subclasses must implement decode()")
