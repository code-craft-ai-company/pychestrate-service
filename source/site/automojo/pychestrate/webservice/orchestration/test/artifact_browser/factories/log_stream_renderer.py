"""
.. module:: orchestration.test.artifact_browser.factories.log_stream_renderer
    :synopsis: LogStreamRenderer — high-confidence renderer for log files.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.artifact_browser.factories.renderer_protocol import (
    ArtifactRendererProtocol,
    CONFIDENCE_NONE,
    CONFIDENCE_PRECISE,
    CONFIDENCE_TYPE_MATCH,
    RendererMatch,
    RendererRecord,
)


LOG_STREAM_RENDERER_TAG: str = "px-log-stream"
LOG_FILE_SUFFIXES: tuple = (".log", ".log.gz", ".out", ".err")
LOG_CLASSIFIER_TAGS: tuple = ("log", "stdout", "stderr")


class LogStreamRenderer(ArtifactRendererProtocol):
    """
        Reference renderer for log files. Wins over the
        :class:`PlainTextRenderer` whenever the artifact looks
        log-shaped — tag-based hits return ``CONFIDENCE_PRECISE``,
        suffix-based hits return ``CONFIDENCE_TYPE_MATCH``.
    """

    factory_protocol_name: str = "artifact_renderer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 900

    @classmethod
    def renderer_record(cls) -> RendererRecord:
        rtnval = RendererRecord(
            component_tag=LOG_STREAM_RENDERER_TAG,
            bundle_url="/web/components/px-log-stream.js",
            description="Streaming log viewer with follow-mode.",
        )
        return rtnval

    @classmethod
    def match(cls, *, artifact) -> RendererMatch:
        classifier_tag = (artifact.classifier_tag or "").lower()
        if classifier_tag in LOG_CLASSIFIER_TAGS:
            rtnval = RendererMatch(
                confidence=CONFIDENCE_PRECISE,
                ttl_seconds=120,
            )
            return rtnval

        name = (artifact.name or "").lower()
        for suffix in LOG_FILE_SUFFIXES:
            if name.endswith(suffix):
                rtnval = RendererMatch(
                    confidence=CONFIDENCE_TYPE_MATCH,
                    ttl_seconds=120,
                )
                return rtnval

        rtnval = RendererMatch(
            confidence=CONFIDENCE_NONE,
            ttl_seconds=0,
        )
        return rtnval
