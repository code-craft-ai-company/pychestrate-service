"""
.. module:: webhooks_out.factories.notification_channel_protocol
    :synopsis: ``notification_channel`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class NotificationChannelProtocol(FactoryProtocolBase):
    """
        Contract for ``notification_channel`` extensions. M1
        ships only the webhook channel; M2 widens to email,
        slack, pagerduty, etc.
    """

    factory_protocol_name: str = "notification_channel"
    protocol_schema_version: int = 1

    @classmethod
    def channel_name(cls) -> str:
        """
            Stable identifier the alert / notification routers
            use to bind a target to a channel.
        """
        raise NotImplementedError("Subclasses must implement channel_name")

    @classmethod
    def supported_signature_schemes(cls) -> Tuple[str, ...]:
        """
            Tuple of signature scheme identifiers this channel
            accepts on outbound deliveries.
        """
        raise NotImplementedError(
            "Subclasses must implement supported_signature_schemes",
        )
