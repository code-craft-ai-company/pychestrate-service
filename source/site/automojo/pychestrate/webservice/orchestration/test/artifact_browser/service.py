"""
.. module:: orchestration.test.artifact_browser.service
    :synopsis: Artifact-browser facade — renderer dispatch.

M1 ships the renderer-selection algorithm only — the framework
walks every registered :class:`ArtifactRendererProtocol`,
invokes ``match`` against the supplied :class:`ArtifactRef`, and
returns the highest-confidence :class:`RendererChoice`. The
listing + signed-download endpoints land in M2 once the
``5-artifact-store`` boundary plumbs object-store access through
this service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Optional, Tuple, Type

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.orchestration.test.artifact_browser.errors import (
    ArtifactPathInvalidError,
    NoMatchingRendererError,
)
from automojo.pychestrate.webservice.orchestration.test.artifact_browser.factories.renderer_protocol import (
    ArtifactRendererProtocol,
    CONFIDENCE_NONE,
    RendererRecord,
)


ARTIFACT_RENDERER_PROTOCOL: str = "artifact_renderer"


@dataclass(frozen=True)
class ArtifactRef:
    """
        Caller-supplied artifact descriptor used by
        :func:`select_renderer`.

        :param run_id: Owning run id (recorded on the choice for
                       observability — the M2 cache layer keys
                       on it).
        :param path: Logical path inside the result tree. Leading
                     slashes are tolerated; ``..`` segments are
                     rejected.
        :param name: File name (last path segment).
        :param content_type: MIME type from the object-store
                             metadata, or ``""`` when unknown.
        :param classifier_tag: Tag from
                               :mod:`5-result-ingest-watcher`,
                               e.g. ``"log"`` or ``"junit"``.
        :param size_bytes: Size in bytes; M1 ignores this but
                           M2 thresholds use it.
    """
    run_id: str
    path: str
    name: str
    content_type: str = ""
    classifier_tag: str = ""
    size_bytes: int = 0


@dataclass(frozen=True)
class RendererChoice:
    """
        Caller-facing read-model — the WebComponent the M2
        front-end mounts plus the cache TTL.
    """
    component_tag: str
    bundle_url: str
    confidence: int
    ttl_seconds: int
    artifact_path: str
    run_id: str


def select_renderer(*, artifact: ArtifactRef) -> RendererChoice:
    """
        Walk every registered renderer, invoke ``match``, and
        return the highest-confidence :class:`RendererChoice`.
        Ties are broken by registration order — the registry
        already orders implementations by PRECEDENCE so the
        operator-preferred renderer wins.

        :raises: ArtifactPathInvalidError on path-traversal
                 attempts.
        :raises: NoMatchingRendererError when no registered
                 renderer matches.
    """
    _validate_path(path=artifact.path)
    candidates = list_factory_implementations(
        factory_protocol_name=ARTIFACT_RENDERER_PROTOCOL,
    )

    best_impl: Optional[Type[ArtifactRendererProtocol]] = None
    best_confidence: int = CONFIDENCE_NONE
    best_ttl: int = 0

    for impl in candidates:
        decision = impl.match(artifact=artifact)
        if decision.confidence > best_confidence:
            best_confidence = decision.confidence
            best_impl = impl
            best_ttl = decision.ttl_seconds

    if best_impl is None or best_confidence == CONFIDENCE_NONE:
        err_lines = ["No registered renderer accepted the artifact."]
        err_lines.append("RUN_ID: {}".format(artifact.run_id))
        err_lines.append("PATH: {}".format(artifact.path))
        err_lines.append("CONTENT_TYPE: {}".format(artifact.content_type))
        err_lines.append("CLASSIFIER_TAG: {}".format(artifact.classifier_tag))
        err_msg = os.linesep.join(err_lines)
        raise NoMatchingRendererError(err_msg) from None

    record = best_impl.renderer_record()
    rtnval = RendererChoice(
        component_tag=record.component_tag,
        bundle_url=record.bundle_url,
        confidence=best_confidence,
        ttl_seconds=best_ttl,
        artifact_path=artifact.path,
        run_id=artifact.run_id,
    )
    return rtnval


def list_renderer_records() -> Tuple[RendererRecord, ...]:
    """
        Enumerate the static :class:`RendererRecord`s of every
        registered renderer in PRECEDENCE order. Useful for
        admin UI listings.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=ARTIFACT_RENDERER_PROTOCOL,
    )
    rtnval = tuple(impl.renderer_record() for impl in candidates)
    return rtnval


def _validate_path(*, path: str) -> None:
    """
        Reject path-traversal attempts before any object-store
        call. M1 keeps the rule simple — ``..`` anywhere in the
        path raises.
    """
    if path is None:
        err_lines = ["Artifact path must not be None."]
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None
    if ".." in path.split("/"):
        err_lines = ["Artifact path may not contain '..' segments."]
        err_lines.append("PATH: {}".format(path))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None
    return
