"""
.. module:: orchestration.test.artifact_browser.factories.renderer_protocol
    :synopsis: ``artifact_renderer`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


# Confidence band constants — the service picks the highest
# confidence among candidates. M1 callers wire through
# ``CONFIDENCE_NONE`` to mean "not my type" and the candidates
# above it.
CONFIDENCE_NONE: int = 0
CONFIDENCE_GENERIC: int = 100
CONFIDENCE_TYPE_MATCH: int = 500
CONFIDENCE_PRECISE: int = 900
CONFIDENCE_MAX: int = 1000


@dataclass(frozen=True)
class RendererRecord:
    """
        Static description of a renderer registered with the
        host. Surfaced to UIs that enumerate the catalog and to
        the M2 ``select_renderer`` REST endpoint.

        :param component_tag: WebComponent tag (e.g.
                              ``px-log-stream``).
        :param bundle_url: URL the M2 plugin loader fetches.
        :param description: Short description.
    """
    component_tag: str
    bundle_url: str
    description: str


@dataclass(frozen=True)
class RendererMatch:
    """
        Per-call match decision returned by
        :meth:`ArtifactRendererProtocol.match`.

        :param confidence: Higher wins. Use the
                           ``CONFIDENCE_*`` constants for
                           interoperability — ``CONFIDENCE_NONE``
                           means "I do not handle this".
        :param ttl_seconds: How long the chosen
                            :class:`RendererChoice` remains
                            valid; the M2 cache layer reads this
                            verbatim.
    """
    confidence: int
    ttl_seconds: int


class ArtifactRendererProtocol(FactoryProtocolBase):
    """
        Contract for ``artifact_renderer`` extensions. A renderer
        decides — given a content-type, classifier tag, file
        name, and size — whether it can present the artifact and
        with what confidence; the framework picks the highest-
        confidence candidate.
    """

    factory_protocol_name: str = "artifact_renderer"
    protocol_schema_version: int = 1

    @classmethod
    def renderer_record(cls) -> RendererRecord:
        """
            Return the renderer's static description.
        """
        raise NotImplementedError("Subclasses must implement renderer_record")

    @classmethod
    def match(
            cls,
            *,
            artifact  # ArtifactRef — avoid circular import
        ) -> RendererMatch:
        """
            Return the renderer's confidence in handling
            ``artifact``.
        """
        raise NotImplementedError("Subclasses must implement match")
