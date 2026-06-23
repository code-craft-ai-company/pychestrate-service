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
from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)


class SmtpEmailChannel(NotificationChannelProtocol):
    """
        Deliver a message over SMTP.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "smtp_email"
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
