"""
.. module:: orchestration.test.catalog.payloads
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: IO shapes for the test catalog.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ImporterEntryPayload:
    """
        Shape an importer factory produces. The catalog stores the
        ``raw_metadata`` dict verbatim so a re-import only changes
        the rendered fields when the importer's view of the source
        changed.

        :param entry_key: Stable identifier the importer assigns —
                          unique per (project, importer_tag).
        :param display_name: Human-readable label.
        :param description: Free-form description string.
        :param required_capability_tags: Capabilities the target
                                         pod must advertise.
        :param param_schema: Parameter-schema dict the orchestrator
                             validates inputs against.
        :param raw_metadata: Importer passthrough.
    """
    entry_key: str
    display_name: str
    description: str
    required_capability_tags: Tuple[str, ...]
    param_schema: Mapping[str, Any]
    raw_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class TestCatalogEntryView:
    """
        Read-model returned to callers (REST / orchestrator).

        :param entry_id: Server-assigned UUID.
        :param project_id: Owning project UUID.
        :param importer_tag: Identifier of the importer that
                             produced the entry.
        :param entry_key: Stable importer-supplied key.
        :param display_name: Human-readable label.
        :param description: Free-form description.
        :param required_capability_tags: Capability tag set.
        :param param_schema: Parameter-schema dict.
        :param raw_metadata: Importer passthrough.
        :param canonical_digest: SHA-256 of the canonical encoding.
        :param retired: Whether the entry has been retired.
        :param updated_at: Last upsert timestamp.
    """
    entry_id: str
    project_id: str
    importer_tag: str
    entry_key: str
    display_name: str
    description: str
    required_capability_tags: Tuple[str, ...]
    param_schema: Mapping[str, Any]
    raw_metadata: Mapping[str, Any]
    canonical_digest: str
    retired: bool
    updated_at: datetime


@dataclass(frozen=True)
class TestCatalogEntrySnapshot:
    """
        Frozen view the orchestrator captures at trigger time. The
        digest lets the dispatcher detect mid-flight catalog drift.

        :param entry_id: Catalog entry UUID.
        :param canonical_digest: Digest of the canonical encoding.
        :param required_capability_tags: Capability tag tuple.
        :param param_schema: Parameter-schema dict.
        :param runner_kind: Resolved runner-kind string copied
                            from ``raw_metadata.runner_kind``.
        :param raw_metadata: Importer passthrough.
    """
    entry_id: str
    canonical_digest: str
    required_capability_tags: Tuple[str, ...]
    param_schema: Mapping[str, Any]
    runner_kind: str
    raw_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class CatalogListFilters:
    """
        Optional filters for ``list_entries``.
    """
    importer_tag: Optional[str] = None
    capability_tag: Optional[str] = None
    include_retired: bool = False
