"""
.. module:: notifications.factories.webhook_channels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webhook-style :class:`NotificationChannelProtocol` implementations.

.. moduleauthor:: Code Craft AI LLC

Ships four reference channels used throughout the Pychestrate docs:

- :class:`SlackWebhookChannel` — ``channel_kind='slack_webhook'``.
- :class:`MsTeamsWebhookChannel` — ``channel_kind='ms_teams_webhook'``.
- :class:`PagerDutyEventsV2Channel` — ``channel_kind='pagerduty_events_v2'``.
- :class:`GenericWebhookChannel` — ``channel_kind='generic_webhook'``.

Each channel POSTs a JSON body to the URL in ``channel_config['url']``.
Tests monkeypatch :func:`_post_json` to avoid real network traffic.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import time

from typing import Any, ClassVar, Mapping, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelConfigField,
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
    kind_label: ClassVar[str] = "Slack"
    kind_description: ClassVar[str] = "Post a message to a Slack channel through an incoming webhook."
    recipient_help: ClassVar[str] = "A Slack channel such as #builds, or leave the webhook's own channel with any text."
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="url", label="Webhook URL", help="The incoming-webhook address Slack gave you. It works like a password, so it is stored in the secrets vault.", secret=True, field_type="url"),
        ChannelConfigField(name="username", label="Name shown in Slack", help="The sender name on each message.", required=False, default="Pychestrate"),
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
    kind_label: ClassVar[str] = "Microsoft Teams"
    kind_description: ClassVar[str] = "Post a card to a Teams channel through an incoming webhook."
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="url", label="Webhook URL", help="The incoming-webhook address Teams gave you. It works like a password, so it is stored in the secrets vault.", secret=True, field_type="url"),
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
    kind_label: ClassVar[str] = "PagerDuty"
    kind_description: ClassVar[str] = "Open an incident through a PagerDuty Events API v2 integration."
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="routing_key", label="Integration key", help="The routing key of the PagerDuty integration. Stored in the secrets vault.", secret=True),
        ChannelConfigField(name="severity", label="Severity", help="critical, error, warning or info.", required=False, default="error"),
        ChannelConfigField(name="source", label="Source", help="The source named on each incident.", required=False, default="pychestrate"),
        ChannelConfigField(name="url", label="Events API address", help="Only change this for a PagerDuty-compatible service.", required=False, field_type="url"),
    )
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
    kind_label: ClassVar[str] = "Webhook (JSON)"
    kind_description: ClassVar[str] = "Send the message as a JSON POST to any address."
    recipient_help: ClassVar[str] = "Any text; it is sent in the \"recipient\" member of the JSON body."
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="url", label="Address", help="Where to POST, starting http:// or https://.", field_type="url"),
        ChannelConfigField(name="authorization", label="Authorization header", help="The full value to send as the Authorization header, for example \"Bearer abc123\". Stored in the secrets vault.", required=False, secret=True),
        ChannelConfigField(name="headers", label="Other headers", help="Headers to add, as a JSON object.", required=False, field_type="mapping"),
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
        url = channel_config.get("url", "")
        payload = {
            "subject": subject,
            "body": body,
            "recipient": recipient,
        }
        headers = dict(channel_config.get("headers", {}) or {})
        authorization = channel_config.get("authorization", None)
        if authorization is not None and len(str(authorization)) > 0:
            headers["Authorization"] = str(authorization)
        rtnval = _send_webhook(url=url, payload=payload, headers=headers)
        return rtnval
