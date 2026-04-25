"""
.. module:: webhooks_out.events
    :synopsis: Webhooks-out bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class WebhookOutEventTopics:
    """
        Webhooks-out bus topics.
    """
    TARGET_REGISTERED = "entity.webhook_out.target_registered"
    TARGET_DISABLED = "entity.webhook_out.target_disabled"
    DELIVERY_ATTEMPTED = "entity.webhook_out.delivery_attempted"
    DELIVERY_FAILED = "entity.webhook_out.delivery_failed"
