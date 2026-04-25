"""
.. module:: orchestration.build.artifacts.events
    :synopsis: Build-artifacts bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class BuildArtifactEventTopics:
    """
        Build-artifacts bus topics. M1 emits MANIFEST_SYNTHESIZED
        + PROMOTED + CHANNEL_HEAD_ADVANCED; M2 wires the
        promotion-denied + rolled-back diagnostics.
    """
    MANIFEST_SYNTHESIZED = "entity.build.artifact.manifest_synthesized"
    PROMOTED = "entity.build.artifact.promoted"
    CHANNEL_HEAD_ADVANCED = "entity.build.artifact.channel_head_advanced"
    PROMOTION_DENIED = "entity.build.artifact.promotion_denied"
    ROLLED_BACK = "entity.build.artifact.rolled_back"
