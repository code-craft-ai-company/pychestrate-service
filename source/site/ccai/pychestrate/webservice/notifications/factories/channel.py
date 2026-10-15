"""
.. module:: notifications.factories.channel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``notification_channel`` factory protocol base.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


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


@dataclass(frozen=True)
class ChannelConfigField:
    """
        One setting of a channel kind, declared so the service can check a
        channel's configuration when it is created and the Notifications page
        can draw its form.

        :param name: Key in the channel's ``config`` mapping.
        :param label: Short name shown beside the input.
        :param help: One sentence telling the administrator what to enter.
        :param required: Whether the setting must be present.
        :param secret: Whether the value is a credential. A secret is stored in
                       the secrets vault and the channel keeps only a
                       ``secret://`` reference to it (see
                       ``specs/2-notification-hub/design.md``).
        :param field_type: ``text``, ``number``, ``bool`` or ``url``
                           (an ``http://`` or ``https://`` address).
        :param default: What the form pre-fills, or None.
    """
    name: str
    label: str
    help: str = ""
    required: bool = True
    secret: bool = False
    field_type: str = "text"
    default: Any = None


class NotificationChannelProtocol(FactoryProtocolBase):
    """
        Contract implemented by each notification channel.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    protocol_schema_version: ClassVar[int] = 1
    channel_kind: ClassVar[str] = ""

    #: What the Notifications page calls this kind, and a sentence on what it does.
    kind_label: ClassVar[str] = ""
    kind_description: ClassVar[str] = ""

    #: What a routing rule's recipient means for this kind (shown beside the recipient input).
    recipient_help: ClassVar[str] = "Any text that names who or what this is for."

    #: The settings of this kind. Empty means "not declared": the configuration is stored as given.
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = ()

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "/docs/extensions/protocols/notification_channel.html"
    )
    published_reference: ClassVar[str] = (
        "ccai.pychestrate.webservice.notifications.factories.smtp_email"
        ".SmtpEmailChannel"
    )

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
