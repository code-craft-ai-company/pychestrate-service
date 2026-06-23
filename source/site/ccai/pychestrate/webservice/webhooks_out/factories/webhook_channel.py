"""
.. module:: webhooks_out.factories.webhook_channel
    :synopsis: WebhookNotificationChannel — reference HTTPS channel.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.webhooks_out.factories.notification_channel_protocol import (
    NotificationChannelProtocol,
)


WEBHOOK_CHANNEL_NAME: str = "webhook"
WEBHOOK_SUPPORTED_SCHEMES: Tuple[str, ...] = ("hmac_sha256",)


class WebhookNotificationChannel(NotificationChannelProtocol):
    """
        Reference HTTPS webhook channel. Carries the M2 HTTP
        delivery boundary; M1 callers exercise the
        signing + persistence path through the service helpers.
    """

    factory_protocol_name: str = "notification_channel"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def channel_name(cls) -> str:
        rtnval = WEBHOOK_CHANNEL_NAME
        return rtnval

    @classmethod
    def supported_signature_schemes(cls) -> Tuple[str, ...]:
        rtnval = WEBHOOK_SUPPORTED_SCHEMES
        return rtnval
