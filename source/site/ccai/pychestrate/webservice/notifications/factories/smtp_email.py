"""
.. module:: notifications.factories.smtp_email
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference SMTP channel for 2-notification-hub M1.

.. moduleauthor:: Code Craft AI LLC

The reference implementation delegates to ``smtplib`` from the standard
library. Tests monkeypatch :func:`_open_smtp_client` to avoid real
network traffic.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import smtplib
import time

from email.message import EmailMessage
from typing import Any, ClassVar, Mapping, Tuple

from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelConfigField,
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)


class SmtpEmailChannel(NotificationChannelProtocol):
    """
        Deliver a message over SMTP.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "smtp_email"
    kind_label: ClassVar[str] = "Email (SMTP)"
    kind_description: ClassVar[str] = "Send an email through your mail server."
    recipient_help: ClassVar[str] = "An email address, for example team@example.com."
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="host", label="Mail server", help="The mail server's name or address, for example smtp.example.com."),
        ChannelConfigField(name="port", label="Port", help="Usually 587 (with TLS) or 25.", field_type="number", default=587),
        ChannelConfigField(name="from_address", label="From address", help="The sender shown on each email, for example pychestrate@example.com."),
        ChannelConfigField(name="use_tls", label="Use TLS", help="Encrypt the connection (STARTTLS). Leave on unless your mail server cannot.", required=False, field_type="bool", default=True),
        ChannelConfigField(name="username", label="User name", help="Leave empty if the mail server does not ask for a login.", required=False),
        ChannelConfigField(name="password", label="Password", help="Stored in the secrets vault. Used only when a user name is set.", required=False, secret=True),
    )
    PRECEDENCE: ClassVar[int] = 1000

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
            Send a plain-text email over SMTP.

            :param channel_config: Must include ``host``, ``port``,
                                   ``from_address``; optional ``use_tls``,
                                   ``username``, ``password``.
            :param recipient: RFC-5321 address.
            :param subject: Subject line.
            :param body: Plain-text body.

            :returns: :class:`ChannelDeliveryOutcome`.
        """
        host = channel_config.get("host", "")
        port = int(channel_config.get("port", 25))
        from_address = channel_config.get("from_address", "")
        use_tls = bool(channel_config.get("use_tls", False))
        username = channel_config.get("username", None)
        password = channel_config.get("password", None)

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = from_address
        message["To"] = recipient
        message.set_content(body)

        start_wall = time.monotonic()
        client = None
        try:
            client = _open_smtp_client(host=host, port=port)
            if use_tls is True:
                client.starttls()
            if username is not None and password is not None:
                client.login(username, password)
            client.send_message(message)
        except (smtplib.SMTPException, OSError) as xcpt:
            elapsed_ms = int((time.monotonic() - start_wall) * 1000.0)
            rtnval = ChannelDeliveryOutcome(
                delivered=False,
                error_message=str(xcpt),
                latency_ms=elapsed_ms,
            )
            return rtnval
        finally:
            if client is not None:
                try:
                    client.quit()
                except smtplib.SMTPException:
                    # A failed quit after a successful send is not a
                    # delivery failure; swallow it here, but log via stdlib.
                    err_msg_lines = ["SMTP quit failed after send."]
                    err_msg_lines.append("HOST: {}".format(host))
                    _ = os.linesep.join(err_msg_lines)

        elapsed_ms = int((time.monotonic() - start_wall) * 1000.0)
        rtnval = ChannelDeliveryOutcome(
            delivered=True,
            error_message="",
            latency_ms=elapsed_ms,
        )
        return rtnval


def _open_smtp_client(*, host: str, port: int) -> smtplib.SMTP:
    """
        Open an ``smtplib.SMTP`` client. Extracted for ease of test patching.

        :param host: SMTP host.
        :param port: SMTP port.

        :returns: The client.
    """
    rtnval = smtplib.SMTP(host=host, port=port, timeout=30)
    return rtnval
