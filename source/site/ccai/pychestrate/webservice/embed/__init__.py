"""
.. module:: webservice.embed
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``8-embeddable-views`` — signed-URL embedding for external portals.

.. moduleauthor:: Code Craft AI LLC

This package implements the public-facing embed surface: external
portals (status pages, kiosks, marketing sites) consume signed URLs
issued under ``/api/v1/projects/{id}/embeds`` and serve them under
``/embed/<view_kind>/<resource_id>``. The signing primitives are
framework-free and live in :mod:`embed.signing`; the view-kind
catalog (a fixed five-entry set) lives in :mod:`embed.view_catalog`.

M1 ships the catalog + the issue / verify primitives with full
property coverage. The rendering controller, vault integration, and
DB-backed audit / signing-key storage land in M2 / M3.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.embed.signing import (
    EmbedSigningKey,
    SignatureVerificationFailure,
    SignedEmbedUrl,
    VerificationOutcome,
    issue_signed_url,
    verify_signed_url,
)
from ccai.pychestrate.webservice.embed.view_catalog import (
    EMBED_NAMESPACE_PREFIX,
    EmbedViewKind,
    VIEW_KIND_ARTIFACT_PREVIEW,
    VIEW_KIND_PIPELINE_DAG,
    VIEW_KIND_PROJECT_DASHBOARD_TILE,
    VIEW_KIND_RUN_DETAIL,
    VIEW_KIND_RUN_LOG_STREAM,
    get_view_kind,
    list_view_kinds,
)


__all__ = [
    "EMBED_NAMESPACE_PREFIX",
    "EmbedSigningKey",
    "EmbedViewKind",
    "SignatureVerificationFailure",
    "SignedEmbedUrl",
    "VIEW_KIND_ARTIFACT_PREVIEW",
    "VIEW_KIND_PIPELINE_DAG",
    "VIEW_KIND_PROJECT_DASHBOARD_TILE",
    "VIEW_KIND_RUN_DETAIL",
    "VIEW_KIND_RUN_LOG_STREAM",
    "VerificationOutcome",
    "get_view_kind",
    "issue_signed_url",
    "list_view_kinds",
    "verify_signed_url",
]
