"""
.. module:: webhooks_out.events
    :synopsis: Webhooks-out bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class WebhookOutEventTopics:
    """
        Webhooks-out bus topics.
    """
    TARGET_REGISTERED = "entity.webhook_out.target_registered"
    TARGET_ENABLED = "entity.webhook_out.target_enabled"
    TARGET_DISABLED = "entity.webhook_out.target_disabled"
    DELIVERY_ATTEMPTED = "entity.webhook_out.delivery_attempted"
    DELIVERY_FAILED = "entity.webhook_out.delivery_failed"
