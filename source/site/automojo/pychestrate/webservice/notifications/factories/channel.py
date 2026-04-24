"""
.. module:: notifications.factories.channel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``notification_channel`` factory protocol base.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ChannelDeliveryOutcome:
    """
        Result of a single :meth:`NotificationChannelProtocol.send` call.

        :param delivered: True on success, False on failure.
        :param error_message: Optional human-readable error.
        :param latency_ms: Measured round-trip time in ms.
    """
    delivered: bool
    error_message: str
    latency_ms: int


class NotificationChannelProtocol(FactoryProtocolBase):
    """
        Contract implemented by each notification channel.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    protocol_schema_version: ClassVar[int] = 1
    channel_kind: ClassVar[str] = ""

    @classmethod
    def send(
            cls,
            *,
            channel_config: Mapping[str, Any],
            recipient: str,
            subject: str,
            body: str
        ) -> ChannelDeliveryOutcome:
        """
            Deliver one message to a single recipient.

            :param channel_config: Channel-specific configuration mapping.
            :param recipient: Target address (email, webhook URL, ...).
            :param subject: Subject line.
            :param body: Rendered body.

            :returns: The :class:`ChannelDeliveryOutcome`.
        """
        raise NotImplementedError("Subclasses must implement send()")
