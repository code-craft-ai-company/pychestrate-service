"""
.. module:: orchestration.test.compare.factories.generic_two_pane_viewer
    :synopsis: GenericTwoPaneDiffViewer — fallback diff viewer.

The generic viewer accepts any artifact pair and returns a
``GENERIC`` confidence so more specific diff viewers always
win.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.compare.factories.diff_viewer_protocol import (
    ArtifactDiffViewerProtocol,
    DIFF_CONFIDENCE_GENERIC,
    DiffViewerMatch,
    DiffViewerRecord,
)


GENERIC_TWO_PANE_VIEWER_TAG: str = "px-two-pane-diff"


class GenericTwoPaneDiffViewer(ArtifactDiffViewerProtocol):
    """
        Reference fallback diff viewer.
    """

    factory_protocol_name: str = "artifact_diff_viewer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def viewer_record(cls) -> DiffViewerRecord:
        rtnval = DiffViewerRecord(
            component_tag=GENERIC_TWO_PANE_VIEWER_TAG,
            bundle_url="/web/components/px-two-pane-diff.js",
            description="Generic two-pane diff viewer for any artifact pair.",
        )
        return rtnval

    @classmethod
    def match(cls, *, artifact) -> DiffViewerMatch:
        rtnval = DiffViewerMatch(
            confidence=DIFF_CONFIDENCE_GENERIC,
            ttl_seconds=300,
        )
        return rtnval
