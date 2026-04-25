"""
.. module:: orchestration.test.artifact_browser.factories.plain_text_renderer
    :synopsis: PlainTextRenderer — generic text/* fallback.

The plain-text renderer accepts any text-like artifact and the
generic ``application/octet-stream`` fallback. It returns a
``GENERIC`` confidence so more specific renderers always win.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.artifact_browser.factories.renderer_protocol import (
    ArtifactRendererProtocol,
    CONFIDENCE_GENERIC,
    CONFIDENCE_NONE,
    RendererMatch,
    RendererRecord,
)


PLAIN_TEXT_RENDERER_TAG: str = "px-plain-text"


class PlainTextRenderer(ArtifactRendererProtocol):
    """
        Reference renderer for ``text/*`` and the
        ``application/octet-stream`` fallback.
    """

    factory_protocol_name: str = "artifact_renderer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def renderer_record(cls) -> RendererRecord:
        rtnval = RendererRecord(
            component_tag=PLAIN_TEXT_RENDERER_TAG,
            bundle_url="/web/components/px-plain-text.js",
            description="Generic text + octet-stream renderer.",
        )
        return rtnval

    @classmethod
    def match(cls, *, artifact) -> RendererMatch:
        content_type = (artifact.content_type or "").lower()
        if content_type.startswith("text/"):
            rtnval = RendererMatch(
                confidence=CONFIDENCE_GENERIC,
                ttl_seconds=300,
            )
            return rtnval
        if content_type in ("", "application/octet-stream"):
            rtnval = RendererMatch(
                confidence=CONFIDENCE_GENERIC,
                ttl_seconds=300,
            )
            return rtnval
        rtnval = RendererMatch(
            confidence=CONFIDENCE_NONE,
            ttl_seconds=0,
        )
        return rtnval
