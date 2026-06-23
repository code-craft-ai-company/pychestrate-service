"""
.. module:: identity.flags.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-feature-flags.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class FlagEventTopics:
    """
        String constants for every entity topic owned by 1-feature-flags.
    """

    FLAG_CREATED: str = "entity.flag.created"
    FLAG_UPDATED: str = "entity.flag.updated"
    FLAG_RETIRED: str = "entity.flag.retired"
    FLAG_REMOVED: str = "entity.flag.removed"
    BACKEND_UNHEALTHY: str = "entity.flag.backend.unhealthy"
    BACKEND_HEALTHY: str = "entity.flag.backend.healthy"
