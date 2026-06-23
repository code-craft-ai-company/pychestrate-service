"""
.. module:: orchestration.test.compare.factories.diff_viewer_protocol
    :synopsis: ``artifact_diff_viewer`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


# Confidence bands — same convention as the artifact-browser
# renderer protocol so operators can reason about the two
# registries together.
DIFF_CONFIDENCE_NONE: int = 0
DIFF_CONFIDENCE_GENERIC: int = 100
DIFF_CONFIDENCE_TYPE_MATCH: int = 500
DIFF_CONFIDENCE_PRECISE: int = 900


@dataclass(frozen=True)
class DiffViewerRecord:
    """
        Static description of a diff-viewer extension. The M2
        run-detail UI fetches the bundle URL.

        :param component_tag: WebComponent tag (e.g.
                              ``px-two-pane-diff``).
        :param bundle_url: URL the M2 plugin loader fetches.
        :param description: Short description.
    """
    component_tag: str
    bundle_url: str
    description: str


@dataclass(frozen=True)
class DiffViewerMatch:
    """
        Per-call match decision returned by
        :meth:`ArtifactDiffViewerProtocol.match`.

        :param confidence: Higher wins.
                           ``DIFF_CONFIDENCE_NONE`` means "I do
                           not handle this".
        :param ttl_seconds: How long the chosen
                            :class:`DiffViewerChoice` remains
                            valid.
    """
    confidence: int
    ttl_seconds: int


class ArtifactDiffViewerProtocol(FactoryProtocolBase):
    """
        Contract for ``artifact_diff_viewer`` extensions.
    """

    factory_protocol_name: str = "artifact_diff_viewer"
    protocol_schema_version: int = 1

    @classmethod
    def viewer_record(cls) -> DiffViewerRecord:
        raise NotImplementedError("Subclasses must implement viewer_record")

    @classmethod
    def match(
            cls,
            *,
            artifact  # DiffArtifactRef — avoid circular import
        ) -> DiffViewerMatch:
        raise NotImplementedError("Subclasses must implement match")
