"""
.. module:: metrics.alerts.events
    :synopsis: Alerts-budgets bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class AlertEventTopics:
    """
        Alerts-budgets bus topics. M1 emits RULE_CREATED +
        RULE_DISABLED + EVALUATED + STATE_CHANGED; M2 wires
        the notification + retry topics.
    """
    RULE_CREATED = "entity.alert.rule_created"
    RULE_UPDATED = "entity.alert.rule_updated"
    RULE_DISABLED = "entity.alert.rule_disabled"
    RULE_DELETED = "entity.alert.rule_deleted"
    EVALUATED = "entity.alert.evaluated"
    STATE_CHANGED = "entity.alert.state_changed"
    FIRED = "entity.alert.fired"
    RESOLVED = "entity.alert.resolved"
