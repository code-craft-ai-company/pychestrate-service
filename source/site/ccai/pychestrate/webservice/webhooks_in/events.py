"""
.. module:: webhooks_in.events
    :synopsis: Webhooks-in event topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class WebhookInEventTopics:
    """
        Stable event-bus topics used by the inbound-webhooks
        feature. The dispatcher emits ``RECEIVED`` for every
        request, ``VERIFIED`` after a successful signature
        compare, ``DISPATCHED`` after the parser publishes its
        normalized events, ``REPLAY_IGNORED`` when the
        replay-cache short-circuits, ``FAILED`` when a
        :class:`StructuredRejection` is produced, and
        ``CONFIGURED`` whenever the configuration service
        creates or mutates a ``webhooks_in_configurations``
        row.
    """
    RECEIVED: str = "entity.webhook.received"
    VERIFIED: str = "entity.webhook.verified"
    DISPATCHED: str = "entity.webhook.dispatched"
    REPLAY_IGNORED: str = "entity.webhook.replay_ignored"
    FAILED: str = "entity.webhook.failed"
    CONFIGURED: str = "entity.webhook.configured"
    CONFIGURATION_DISABLED: str = "entity.webhook.configuration_disabled"
