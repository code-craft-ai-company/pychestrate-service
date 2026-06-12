"""
.. module:: orchestration.infra.guards.events
    :synopsis: Blast-radius-guards bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class GuardEventTopics:
    """
        Blast-radius-guards bus topics.
    """
    ATTACHMENT_SET = "entity.guard.attachment_set"
    ATTACHMENT_DISABLED = "entity.guard.attachment_disabled"
    DECIDED = "entity.guard.decided"
