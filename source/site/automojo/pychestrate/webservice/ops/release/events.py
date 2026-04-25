"""
.. module:: ops.release.events
    :synopsis: Release-channels event topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ReleaseEventTopics:
    """
        Stable event-bus topics for the release-channels
        feature. M1 emits PUBLISHED + CANARY_STARTED on the
        publish path; M2 fills out promotion / rollback /
        manifest verification topics.
    """
    PUBLISHED: str = "entity.release.published"
    PROMOTED: str = "entity.release.promoted"
    ROLLED_BACK: str = "entity.release.rolled_back"
    CANARY_STARTED: str = "entity.release.canary_started"
    POLICY_FALLBACK: str = "entity.release.policy_fallback"
    MANIFEST_REJECTED: str = "entity.release.manifest.rejected"
