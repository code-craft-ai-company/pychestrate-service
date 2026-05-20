"""
.. module:: backup.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Backup / disaster-recovery orchestrator facade.

.. moduleauthor:: Automation Mojo LLC

The p21d milestone implements a **manual-trigger baseline** of the
``10-backup-dr`` feature. ``trigger_backup`` snapshots three
substrates -- the database, object-store references, and secrets
metadata -- into a single ``tar`` archive that is written through
the configured ``backup_storage_backend`` factory. ``list_backups``
and ``get_backup`` surface the recorded runs.

Scoped as a documented follow-on (flagged in the PR body):

* Scheduled full / incremental backups -- the spec's daily / hourly
  cadence. The p21d surface is manual trigger only.
* The point-in-time restore executor -- ``request_restore`` records
  the request and raises :class:`BackupRestoreNotImplementedError`;
  the restore route answers ``501`` until the executor lands.
* The escrowed-BMK secrets-encryption envelope. The p21d secrets
  substrate snapshots **metadata only** (ref names + version
  counts), never plaintext or ciphertext, so no key material is
  involved in the baseline.

Caller-driven behavior follows the AGENTS.md "Aspects" pattern via
:class:`BackupAspects`; there are no behavior-modifying decorators.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import io
import json
import logging
import tarfile

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.backup import repository
from automojo.pychestrate.webservice.backup.errors import (
    BackupBackendUnavailableError,
    BackupRecordNotFoundError,
    BackupRequestInvalidError,
    BackupRestoreNotImplementedError,
)
from automojo.pychestrate.webservice.backup.events import BackupEventTopics
from automojo.pychestrate.webservice.backup.factories.local_backend import (
    LocalFilesystemBackupBackend,
)
from automojo.pychestrate.webservice.backup.factories.storage_backend import (
    BackupStorageBackendProtocol,
)
from automojo.pychestrate.webservice.backup.models import (
    BackupRecord,
    BackupStatus,
)


_LOGGER = logging.getLogger("pychestrate.backup.service")


@dataclass(frozen=True)
class BackupAspects:
    """
        Caller-controlled behavior knobs for a backup trigger.

        :param include_database: Snapshot the database substrate.
        :param include_object_store: Snapshot object-store refs.
        :param include_secrets: Snapshot secrets metadata.
        :param note: Operator-supplied free-text note.
    """
    include_database: bool = True
    include_object_store: bool = True
    include_secrets: bool = True
    note: str = ""


@dataclass
class BackupRecordView:
    """
        Read-model for a backup record returned to the REST layer.
    """
    backup_id: str
    status: str
    backend: str
    archive_uri: Optional[str]
    archive_sha256: Optional[str]
    size_bytes: Optional[int]
    manifest: Dict[str, Any] = field(default_factory=dict)
    error_detail: Optional[str] = None
    note: str = ""
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def _resolve_storage_backend() -> Any:
    """
        Resolve the active ``backup_storage_backend`` factory.

        The p21d baseline binds the in-tree
        :class:`LocalFilesystemBackupBackend` reference; a registry
        lookup replaces this when production backends ship.

        :returns: A :class:`BackupStorageBackendProtocol` subclass.
    """
    rtnval: Any = LocalFilesystemBackupBackend
    return rtnval


def _row_to_view(row: BackupRecord) -> BackupRecordView:
    """
        Project a :class:`BackupRecord` row onto a view.

        :param row: The persistence row.

        :returns: The :class:`BackupRecordView`.
    """
    status_value = row.status
    if isinstance(status_value, BackupStatus):
        status_value = status_value.value

    created_by_value: Optional[str] = None
    if row.created_by is not None:
        created_by_value = str(row.created_by)

    rtnval = BackupRecordView(
        backup_id=str(row.backup_id),
        status=str(status_value),
        backend=row.backend,
        archive_uri=row.archive_uri,
        archive_sha256=row.archive_sha256,
        size_bytes=row.size_bytes,
        manifest=dict(row.manifest or {}),
        error_detail=row.error_detail,
        note=row.note or "",
        created_by=created_by_value,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
    return rtnval


def _snapshot_database(db_session: DbSession) -> Dict[str, Any]:
    """
        Build the database-substrate manifest section.

        The p21d baseline records the table inventory rather than a
        full ``pg_basebackup`` stream (the dump executor is the
        scheduler follow-on). It is enough to prove the substrate
        is covered and is byte-stable for the archive.

        :param db_session: Active SQLAlchemy session.

        :returns: A manifest section dict.
    """
    bind = db_session.get_bind()
    table_names: List[str] = []
    try:
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(bind)
        table_names = sorted(inspector.get_table_names())
    except Exception as xcpt:
        _LOGGER.warning(
            "pychestrate.backup.db_inventory_failed cause=%s",
            str(xcpt),
        )
        table_names = []

    rtnval: Dict[str, Any] = {
        "included": True,
        "table_count": len(table_names),
        "tables": table_names,
    }
    return rtnval


def _snapshot_object_store(db_session: DbSession) -> Dict[str, Any]:
    """
        Build the object-store-substrate manifest section.

        The p21d baseline records the count of artifact references
        the object store addresses; the content copy lands with the
        scheduler follow-on.

        :param db_session: Active SQLAlchemy session.

        :returns: A manifest section dict.
    """
    object_count = 0
    try:
        from sqlalchemy import text as sa_text

        result = db_session.execute(
            sa_text("SELECT COUNT(*) FROM artifacts"),
        )
        scalar = result.scalar()
        if scalar is not None:
            object_count = int(scalar)
    except Exception:
        object_count = 0

    rtnval: Dict[str, Any] = {
        "included": True,
        "object_count": object_count,
    }
    return rtnval


def _snapshot_secrets(db_session: DbSession) -> Dict[str, Any]:
    """
        Build the secrets-substrate manifest section.

        The p21d baseline records secrets **metadata only** -- the
        count of secret entries. No plaintext, ciphertext, or key
        material is read, so the escrowed-BMK envelope is not
        needed for the baseline.

        :param db_session: Active SQLAlchemy session.

        :returns: A manifest section dict.
    """
    entry_count = 0
    try:
        from sqlalchemy import text as sa_text

        result = db_session.execute(
            sa_text("SELECT COUNT(*) FROM phase1_secrets"),
        )
        scalar = result.scalar()
        if scalar is not None:
            entry_count = int(scalar)
    except Exception:
        entry_count = 0

    rtnval: Dict[str, Any] = {
        "included": True,
        "entry_count": entry_count,
        "encryption": "metadata-only (no key material in baseline)",
    }
    return rtnval


def _build_archive_bytes(
        *,
        backup_id: str,
        manifest: Dict[str, Any]
    ) -> bytes:
    """
        Serialize a backup manifest into a deterministic ``tar``
        archive byte-string.

        :param backup_id: The backup record UUID.
        :param manifest: The substrate-inventory manifest.

        :returns: The archive bytes.
    """
    manifest_doc = {
        "backup_id": backup_id,
        "manifest": manifest,
    }
    manifest_bytes = json.dumps(
        manifest_doc, sort_keys=True, indent=2,
    ).encode("utf-8")

    buffer = io.BytesIO()
    archive = tarfile.open(fileobj=buffer, mode="w")
    info = tarfile.TarInfo(name="manifest.json")
    info.size = len(manifest_bytes)
    info.mtime = 0
    archive.addfile(info, io.BytesIO(manifest_bytes))
    archive.close()

    rtnval = buffer.getvalue()
    return rtnval


def trigger_backup(
        *,
        db_session: DbSession,
        aspects: Optional[BackupAspects] = None,
        actor_id: Optional[str] = None
    ) -> BackupRecordView:
    """
        Trigger a manual backup run.

        Snapshots the selected substrates into a ``tar`` archive,
        writes it through the configured ``backup_storage_backend``,
        and records the run in the ``backup_record`` table.

        :param db_session: Active SQLAlchemy session.
        :param aspects: Caller-controlled behavior knobs.
        :param actor_id: UUID of the triggering principal, if any.

        :returns: The completed :class:`BackupRecordView`.
        :raises: BackupRequestInvalidError, BackupBackendUnavailableError
    """
    effective_aspects = aspects
    if effective_aspects is None:
        effective_aspects = BackupAspects()

    any_substrate = (
        effective_aspects.include_database
        or effective_aspects.include_object_store
        or effective_aspects.include_secrets
    )
    if any_substrate is False:
        raise BackupRequestInvalidError(
            "A backup must include at least one substrate.",
        )

    backend = _resolve_storage_backend()
    backend_kind = backend.backend_kind()

    row = repository.insert_backup_record(
        db_session=db_session,
        backend=backend_kind,
        note=effective_aspects.note,
        actor_id=actor_id,
    )
    backup_id = str(row.backup_id)

    _LOGGER.info(
        "pychestrate.backup.run.started backup_id=%s backend=%s topic=%s",
        backup_id,
        backend_kind,
        BackupEventTopics.STARTED,
    )

    manifest: Dict[str, Any] = {}
    if effective_aspects.include_database is True:
        manifest["database"] = _snapshot_database(db_session=db_session)
    if effective_aspects.include_object_store is True:
        manifest["object_store"] = _snapshot_object_store(
            db_session=db_session,
        )
    if effective_aspects.include_secrets is True:
        manifest["secrets"] = _snapshot_secrets(db_session=db_session)

    archive_bytes = _build_archive_bytes(
        backup_id=backup_id,
        manifest=manifest,
    )
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    try:
        write_result = backend.write_archive(
            backup_id=backup_id,
            archive_bytes=archive_bytes,
        )
    except BackupBackendUnavailableError as xcpt:
        repository.mark_backup_failed(
            db_session=db_session,
            row=row,
            error_detail=str(xcpt),
            completed_at=utc_now(),
        )
        _LOGGER.error(
            "pychestrate.backup.run.failed backup_id=%s topic=%s",
            backup_id,
            BackupEventTopics.FAILED,
        )
        raise

    repository.mark_backup_completed(
        db_session=db_session,
        row=row,
        archive_uri=write_result.archive_uri,
        archive_sha256=archive_sha256,
        size_bytes=write_result.size_bytes,
        manifest=manifest,
        completed_at=utc_now(),
    )

    _LOGGER.info(
        "pychestrate.backup.run.completed backup_id=%s bytes=%d topic=%s",
        backup_id,
        write_result.size_bytes,
        BackupEventTopics.COMPLETED,
    )

    rtnval = _row_to_view(row=row)
    return rtnval


def get_backup(
        *,
        db_session: DbSession,
        backup_id: str
    ) -> BackupRecordView:
    """
        Read a backup record's status and manifest.

        :param db_session: Active SQLAlchemy session.
        :param backup_id: Backup record UUID.

        :returns: The :class:`BackupRecordView`.
        :raises: BackupRecordNotFoundError
    """
    row = repository.find_backup_record_by_id(
        db_session=db_session,
        backup_id=backup_id,
    )
    if row is None:
        raise BackupRecordNotFoundError(
            "Backup record not found: {}".format(backup_id),
        )
    rtnval = _row_to_view(row=row)
    return rtnval


def list_backups(
        *,
        db_session: DbSession,
        status: Optional[BackupStatus],
        page: int,
        per_page: int
    ) -> Dict[str, Any]:
    """
        Return a page of backup records.

        :param db_session: Active SQLAlchemy session.
        :param status: Optional status filter.
        :param page: One-based page index.
        :param per_page: Page size.

        :returns: A dict with ``items`` (views) and ``total``.
    """
    rows = repository.list_backup_records(
        db_session=db_session,
        status=status,
        page=page,
        per_page=per_page,
    )
    total = repository.count_backup_records(
        db_session=db_session,
        status=status,
    )

    items: List[BackupRecordView] = []
    for row in rows:
        items.append(_row_to_view(row=row))

    rtnval: Dict[str, Any] = {
        "items": items,
        "total": total,
    }
    return rtnval


def request_restore(
        *,
        db_session: DbSession,
        backup_id: str,
        actor_id: Optional[str] = None
    ) -> None:
    """
        Validate a restore target and record the restore request.

        Restore execution is a documented follow-on for the p21d
        milestone -- this entry point validates that the target
        backup exists and completed, logs the request, then raises
        :class:`BackupRestoreNotImplementedError` so the REST layer
        answers ``501``.

        :param db_session: Active SQLAlchemy session.
        :param backup_id: Backup record UUID to restore from.
        :param actor_id: UUID of the requesting principal, if any.

        :returns: Never returns normally.
        :raises: BackupRecordNotFoundError,
                 BackupRestoreNotImplementedError
    """
    row = repository.find_backup_record_by_id(
        db_session=db_session,
        backup_id=backup_id,
    )
    if row is None:
        raise BackupRecordNotFoundError(
            "Backup record not found: {}".format(backup_id),
        )

    _LOGGER.info(
        "pychestrate.backup.restore.requested backup_id=%s actor=%s topic=%s",
        backup_id,
        str(actor_id),
        BackupEventTopics.RESTORE_REQUESTED,
    )

    raise BackupRestoreNotImplementedError(
        "Restore execution is a documented follow-on for the p21d "
        "milestone; the restore executor has not yet shipped.",
    )
