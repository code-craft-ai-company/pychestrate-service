"""
.. module:: webservice.embed.view_catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Fixed catalog of embeddable view kinds.

.. moduleauthor:: Code Craft AI LLC

The view-kind catalog is intentionally fixed — additions require an
in-tree code review rather than a runtime registration call. Each
view kind names the WebComponent tag the renderer drops onto the
page, the read-scope permission keys an inline token must intersect
to, and whether the kind tolerates anonymous access (kiosk-style
portal).

The catalog data is small enough to live as module-level constants
plus a name-keyed dict; lookup is O(1). The shape mirrors
:class:`EmbedViewKind` so future work that needs to walk the catalog
in catalog order has a stable iteration source.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ccai.errors.exceptions import ConfigurationError


EMBED_NAMESPACE_PREFIX: str = "/embed/"


VIEW_KIND_RUN_DETAIL: str = "run_detail"
VIEW_KIND_RUN_LOG_STREAM: str = "run_log_stream"
VIEW_KIND_ARTIFACT_PREVIEW: str = "artifact_preview"
VIEW_KIND_PIPELINE_DAG: str = "pipeline_dag"
VIEW_KIND_PROJECT_DASHBOARD_TILE: str = "project_dashboard_tile"


@dataclass(frozen=True)
class EmbedViewKind:
    """
        One row in the embed view-kind catalog.

        :param view_kind_name: Stable identifier in URLs and audit
                               records.
        :param declared_read_scope: Permission keys an inline token
                                    must hold (the M2 issuer
                                    intersects this with the issuing
                                    principal's permission set).
        :param supports_anonymous: True iff the kind tolerates an
                                   anonymous embed (e.g.
                                   ``project_dashboard_tile`` on a
                                   public portal).
        :param component_tag: Layer 9 WebComponent the renderer drops
                              onto the page (e.g. ``pyc-run-detail``).
    """
    view_kind_name: str
    declared_read_scope: Tuple[str, ...]
    supports_anonymous: bool
    component_tag: str


_RUN_DETAIL: EmbedViewKind = EmbedViewKind(
    view_kind_name=VIEW_KIND_RUN_DETAIL,
    declared_read_scope=("system:run.read",),
    supports_anonymous=False,
    component_tag="pyc-run-detail",
)


_RUN_LOG_STREAM: EmbedViewKind = EmbedViewKind(
    view_kind_name=VIEW_KIND_RUN_LOG_STREAM,
    declared_read_scope=("system:run.read", "system:run.logs.read"),
    supports_anonymous=False,
    component_tag="pyc-log-stream",
)


_ARTIFACT_PREVIEW: EmbedViewKind = EmbedViewKind(
    view_kind_name=VIEW_KIND_ARTIFACT_PREVIEW,
    declared_read_scope=("system:artifact.read",),
    supports_anonymous=False,
    component_tag="pyc-artifact-preview",
)


_PIPELINE_DAG: EmbedViewKind = EmbedViewKind(
    view_kind_name=VIEW_KIND_PIPELINE_DAG,
    declared_read_scope=("system:pipeline.read",),
    supports_anonymous=False,
    component_tag="pyc-pipeline-dag",
)


_PROJECT_DASHBOARD_TILE: EmbedViewKind = EmbedViewKind(
    view_kind_name=VIEW_KIND_PROJECT_DASHBOARD_TILE,
    declared_read_scope=("system:dashboard.read",),
    supports_anonymous=True,
    component_tag="pyc-metric-tile",
)


_FIXED_VIEW_KINDS: Tuple[EmbedViewKind, ...] = (
    _RUN_DETAIL,
    _RUN_LOG_STREAM,
    _ARTIFACT_PREVIEW,
    _PIPELINE_DAG,
    _PROJECT_DASHBOARD_TILE,
)


_VIEW_KIND_BY_NAME: Dict[str, EmbedViewKind] = {
    entry.view_kind_name: entry for entry in _FIXED_VIEW_KINDS
}


def list_view_kinds() -> List[EmbedViewKind]:
    """
        Return every registered :class:`EmbedViewKind` in catalog
        declaration order.

        :returns: List of :class:`EmbedViewKind`. Caller must not
                  mutate the underlying tuple.
    """
    rtnval = list(_FIXED_VIEW_KINDS)
    return rtnval


def get_view_kind(*, view_kind_name: str) -> EmbedViewKind:
    """
        Resolve a view-kind name to its catalog entry.

        :param view_kind_name: Identifier supplied by the issuer or
                               by the embed URL.

        :returns: :class:`EmbedViewKind`.
        :raises: ConfigurationError on unknown name. Per the spec the
                 catalog is fixed; callers seeing an unknown name are
                 working from a stale build and the failure is loud.
    """
    matched = _VIEW_KIND_BY_NAME.get(view_kind_name, None)
    if matched is None:
        err_msg_lines = ["Unknown embed view kind."]
        err_msg_lines.append("VIEW_KIND_NAME: {}".format(view_kind_name))
        err_msg_lines.append(
            "REGISTERED: {}".format(
                ", ".join(sorted(_VIEW_KIND_BY_NAME.keys()))
            )
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
    rtnval = matched
    return rtnval
