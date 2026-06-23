"""
.. module:: orchestration.infra.environment.events
    :synopsis: Environment-registry bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class EnvironmentEventTopics:
    """
        Environment-registry bus topics.
    """
    DECLARED = "entity.environment.declared"
    UPDATED = "entity.environment.updated"
    ARCHIVED = "entity.environment.archived"
    FROZEN = "entity.environment.frozen"
    UNFROZEN = "entity.environment.unfrozen"
    APPLIED = "entity.environment.applied"
    DESTROYED = "entity.environment.destroyed"
