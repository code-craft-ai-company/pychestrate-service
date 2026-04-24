"""
.. module:: retention.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 2-retention-policies.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class RetentionEventTopics:
    """
        String constants for every entity topic owned by 2-retention-policies.
    """

    RETENTION_APPLIED: str = "entity.retention.applied"
    RETENTION_POLICY_CREATED: str = "entity.retention.policy_created"
    RETENTION_POLICY_PUBLISHED: str = "entity.retention.policy_published"
