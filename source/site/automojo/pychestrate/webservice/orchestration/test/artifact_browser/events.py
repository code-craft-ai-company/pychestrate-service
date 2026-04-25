"""
.. module:: orchestration.test.artifact_browser.events
    :synopsis: Artifact-browser bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ArtifactBrowserEventTopics:
    """
        Artifact-browser bus topics. M1 emits RENDERER_SELECTED
        + NO_MATCH for observability; M2 wires the audit trail
        via 1-audit-log.
    """
    RENDERER_SELECTED = "entity.artifact.renderer_selected"
    NO_MATCH = "entity.artifact.renderer_no_match"
