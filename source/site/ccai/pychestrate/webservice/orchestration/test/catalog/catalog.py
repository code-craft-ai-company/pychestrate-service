"""
.. module:: orchestration.test.catalog.catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Catalog facade — upsert / snapshot / list / retire.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.orchestration.test.catalog import repository
from ccai.pychestrate.webservice.orchestration.test.catalog.canonicalization import (
    canonicalize_entry,
    compute_digest,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.errors import (
    CatalogEntryNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.models import (
    TestCatalogEntry,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
    TestCatalogEntrySnapshot,
    TestCatalogEntryView,
)


def upsert_entry(
        *,
        db_session: DbSession,
        project_id: str,
        importer_tag: str,
        payload: ImporterEntryPayload
    ) -> TestCatalogEntryView:
    """
        Upsert a catalog entry. The natural key is
        ``(project_id, importer_tag, entry_key)``; the digest is
        recomputed every call. ``retired=False`` is restored on
        every upsert so a re-import un-retires.
    """
    canonical = canonicalize_entry(payload=payload)
    digest = compute_digest(canonical_bytes=canonical)
    now = utc_now()

    existing = repository.find_entry(
        db_session=db_session,
        project_id=project_id,
        importer_tag=importer_tag,
        entry_key=payload.entry_key,
    )
    if existing is None:
        existing = TestCatalogEntry(
            entry_id=new_uuid(),
            project_id=project_id,
            importer_tag=importer_tag,
            entry_key=payload.entry_key,
            display_name=payload.display_name,
            description=payload.description,
            required_capability_tags=list(payload.required_capability_tags),
            param_schema=dict(payload.param_schema),
            raw_metadata=dict(payload.raw_metadata),
            canonical_digest=digest,
            retired=False,
            created_at=now,
            updated_at=now,
        )
        db_session.add(existing)
    else:
        existing.display_name = payload.display_name
        existing.description = payload.description
        existing.required_capability_tags = list(payload.required_capability_tags)
        existing.param_schema = dict(payload.param_schema)
        existing.raw_metadata = dict(payload.raw_metadata)
        existing.canonical_digest = digest
        existing.retired = False
        existing.updated_at = now
    db_session.flush()
    db_session.commit()
    rtnval = _row_to_view(row=existing)
    return rtnval


def retire_entry(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> TestCatalogEntryView:
    """
        Mark an entry retired. Idempotent.
    """
    row = repository.find_by_id(db_session=db_session, entry_id=entry_id)
    if row is None:
        err_lines = ["Catalog entry not found."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise CatalogEntryNotFoundError(err_msg) from None
    row.retired = True
    row.updated_at = utc_now()
    db_session.flush()
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def list_entries(
        *,
        db_session: DbSession,
        project_id: str,
        include_retired: bool = False,
        importer_tag: Optional[str] = None,
        capability_tag: Optional[str] = None
    ) -> List[TestCatalogEntryView]:
    """
        Return a project's catalog entries.
    """
    rows = repository.list_entries(
        db_session=db_session,
        project_id=project_id,
        include_retired=include_retired,
        importer_tag=importer_tag,
        capability_tag=capability_tag,
    )
    rtnval = [_row_to_view(row=row) for row in rows]
    return rtnval


def snapshot_for_dispatch(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> TestCatalogEntrySnapshot:
    """
        Capture a frozen snapshot of an active catalog entry for
        the orchestrator to embed in the dispatch envelope. Raises
        :class:`CatalogEntryNotFoundError` when the entry is
        missing or retired.
    """
    row = repository.find_by_id(db_session=db_session, entry_id=entry_id)
    if row is None:
        err_lines = ["Catalog entry not found."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise CatalogEntryNotFoundError(err_msg) from None
    if bool(row.retired) is True:
        err_lines = ["Catalog entry is retired."]
        err_lines.append("ENTRY_ID: {}".format(entry_id))
        err_msg = os.linesep.join(err_lines)
        raise CatalogEntryNotFoundError(err_msg) from None

    raw_metadata = dict(row.raw_metadata or {})
    runner_kind = raw_metadata.get("runner_kind", "testbase")
    if isinstance(runner_kind, str) is False:
        runner_kind = "testbase"
    rtnval = TestCatalogEntrySnapshot(
        entry_id=str(row.entry_id),
        canonical_digest=row.canonical_digest,
        required_capability_tags=tuple(row.required_capability_tags or []),
        param_schema=dict(row.param_schema or {}),
        runner_kind=runner_kind,
        raw_metadata=raw_metadata,
        display_name=str(row.display_name or ""),
    )
    return rtnval


def _row_to_view(*, row) -> TestCatalogEntryView:
    """
        Convert an ORM row to the read-model.
    """
    rtnval = TestCatalogEntryView(
        entry_id=str(row.entry_id),
        project_id=str(row.project_id),
        importer_tag=row.importer_tag,
        entry_key=row.entry_key,
        display_name=row.display_name,
        description=row.description,
        required_capability_tags=tuple(row.required_capability_tags or []),
        param_schema=dict(row.param_schema or {}),
        raw_metadata=dict(row.raw_metadata or {}),
        canonical_digest=row.canonical_digest,
        retired=bool(row.retired),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
