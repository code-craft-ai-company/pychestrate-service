"""
.. module:: resources.usage_history.events
    :synopsis: Usage-history bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class UsageHistoryEventTopics:
    """
        Usage-history bus topics. M1 emits APPENDED and the
        idempotency-suppression diagnostic. M2 wires the
        roll-up + forced-release-burst topics.
    """
    APPENDED = "pychestrate.resource.usage.appended"
    DUPLICATE_SUPPRESSED = "pychestrate.resource.usage.duplicate_suppressed"
