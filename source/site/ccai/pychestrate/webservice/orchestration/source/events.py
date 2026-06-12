"""
.. module:: orchestration.source.events
    :synopsis: Source-integrations bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SourceEventTopics:
    """
        Source-integrations bus topics.
    """
    WEBHOOK_RECEIVED = "entity.source.webhook.received"
    WEBHOOK_DEDUPED = "entity.source.webhook.deduped"
    WEBHOOK_REJECTED = "entity.source.webhook.rejected"
    PIPELINE_TRIGGERED = "entity.source.pipeline_triggered_by_webhook"
    PROJECT_CONFIG_SET = "entity.source.project_config_set"
    LAST_SEEN_HEAD_UPDATED = "entity.source.last_seen_head_updated"
