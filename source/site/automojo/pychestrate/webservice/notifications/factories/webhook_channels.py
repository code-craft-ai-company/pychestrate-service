"""
.. module:: notifications.factories.webhook_channels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webhook-style :class:`NotificationChannelProtocol` implementations.

.. moduleauthor:: Automation Mojo LLC

Ships four reference channels used throughout the Pychestrate docs:

- :class:`SlackWebhookChannel` — ``channel_kind='slack_webhook'``.
- :class:`MsTeamsWebhookChannel` — ``channel_kind='ms_teams_webhook'``.
- :class:`PagerDutyEventsV2Channel` — ``channel_kind='pagerduty_events_v2'``.
- :class:`GenericWebhookChannel` — ``channel_kind='generic_webhook'``.

Each channel POSTs a JSON body to the URL in ``channel_config['url']``.
Tests monkeypatch :func:`_post_json` to avoid real network traffic.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import time

from typing import Any, ClassVar, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from automojo.pychestrate.webservice.notifications.factories.channel import (
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)


def _post_json(*, url: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> int:
    """
        POST a JSON body and return the HTTP status code. Extracted so
        tests can monkeypatch it.

        :param url: Target URL.
        :param payload: JSON-serializable payload.
        :param headers: Optional headers.

        :returns: HTTP status code.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)

    with urllib_request.urlopen(req, timeout=30) as response:
        rtnval = int(response.status)

    return rtnval


def _send_webhook(
        *,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str]
    ) -> ChannelDeliveryOutcome:
    """
        Post ``payload`` to ``url`` and wrap the result in a
        :class:`ChannelDeliveryOutcome`.
    """
    start_wall = time.monotonic()
    try:
        status_code = _post_json(url=url, payload=payload, headers=headers)
    except (urllib_error.URLError, OSError) as xcpt:
        elapsed_ms = int((time.monotonic() - start_wall) * 1000.0)
        rtnval = ChannelDeliveryOutcome(
            delivered=False,
            error_message=str(xcpt),
            latency_ms=elapsed_ms,
        )
        return rtnval

    elapsed_ms = int((time.monotonic() - start_wall) * 1000.0)
    delivered = 200 <= status_code < 300
    error = "" if delivered is True else "Non-2xx status: {}".format(status_code)
    rtnval = ChannelDeliveryOutcome(
        delivered=delivered,
        error_message=error,
        latency_ms=elapsed_ms,
    )
    return rtnval


class SlackWebhookChannel(NotificationChannelProtocol):
    """
        Deliver a Slack message via a configured webhook URL.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "slack_webhook"
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
        url = channel_config.get("url", "")
        payload = {
            "text": "*{}*\n{}".format(subject, body),
            "username": channel_config.get("username", "Pychestrate"),
        }
        if recipient is not None and len(recipient.strip()) > 0:
            payload["channel"] = recipient
        rtnval = _send_webhook(url=url, payload=payload, headers={})
        return rtnval


class MsTeamsWebhookChannel(NotificationChannelProtocol):
    """
        Deliver a card to an MS Teams incoming webhook.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "ms_teams_webhook"
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
        url = channel_config.get("url", "")
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": subject,
            "title": subject,
            "text": body,
        }
        rtnval = _send_webhook(url=url, payload=payload, headers={})
        return rtnval


class PagerDutyEventsV2Channel(NotificationChannelProtocol):
    """
        Route an event via the PagerDuty Events v2 API.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "pagerduty_events_v2"
    PRECEDENCE: ClassVar[int] = 1000
    _DEFAULT_URL: ClassVar[str] = "https://events.pagerduty.com/v2/enqueue"

    @classmethod
    def send(
            cls,
            *,
            channel_config: Mapping[str, Any],
            recipient: str,
            subject: str,
            body: str
        ) -> ChannelDeliveryOutcome:
        url = channel_config.get("url", cls._DEFAULT_URL)
        routing_key = channel_config.get("routing_key", "")
        severity = channel_config.get("severity", "error")
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": recipient if len(recipient.strip()) > 0 else subject,
            "payload": {
                "summary": subject,
                "severity": severity,
                "source": channel_config.get("source", "pychestrate"),
                "custom_details": {"body": body},
            },
        }
        rtnval = _send_webhook(url=url, payload=payload, headers={})
        return rtnval


class GenericWebhookChannel(NotificationChannelProtocol):
    """
        Deliver the rendered message as a generic JSON POST.
    """

    factory_protocol_name: ClassVar[str] = "notification_channel"
    channel_kind: ClassVar[str] = "generic_webhook"
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
        url = channel_config.get("url", "")
        payload = {
            "subject": subject,
            "body": body,
            "recipient": recipient,
        }
        headers = channel_config.get("headers", {}) or {}
        rtnval = _send_webhook(url=url, payload=payload, headers=headers)
        return rtnval
