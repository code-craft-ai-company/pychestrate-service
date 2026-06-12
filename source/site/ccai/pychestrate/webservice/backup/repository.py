"""
.. module:: backup.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CRUD helpers for backup-record rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.backup.models import (
    BackupRecord,
    BackupStatus,
)


def insert_backup_record(
        *,
        db_session: DbSession,
        backend: str,
        note: str,
        actor_id: Optional[str]
    ) -> BackupRecord:
    """
        Insert a fresh backup record in the ``running`` state.

        :param db_session: Active SQLAlchemy session.
        :param backend: Storage-backend kind identifier.
        :param note: Operator-supplied free-text note.
        :param actor_id: UUID of the triggering principal, if any.

        :returns: The inserted :class:`BackupRecord`.
    """
    row = BackupRecord(
        backup_id=new_uuid(),
        status=BackupStatus.RUNNING,
        backend=backend,
        archive_uri=None,
        archive_sha256=None,
        size_bytes=None,
        manifest={},
        error_detail=None,
        note=note,
        created_by=actor_id,
        completed_at=None,
    )
    db_session.add(row)
    db_session.flush()
    rtnval = row
    return rtnval


def find_backup_record_by_id(
        *,
        db_session: DbSession,
        backup_id: str
    ) -> Optional[BackupRecord]:
    """
        Resolve a backup record by id.

        :param db_session: Active SQLAlchemy session.
        :param backup_id: Backup record UUID.

        :returns: The :class:`BackupRecord` or ``None``.
    """
    rtnval = (
        db_session.query(BackupRecord)
        .filter(BackupRecord.backup_id == backup_id)
        .first()
    )
    return rtnval


def list_backup_records(
        *,
        db_session: DbSession,
        status: Optional[BackupStatus],
        page: int,
        per_page: int
    ) -> List[BackupRecord]:
    """
        Return a page of backup records, newest-first.

        :param db_session: Active SQLAlchemy session.
        :param status: Optional status filter.
        :param page: One-based page index.
        :param per_page: Page size.

        :returns: A list of :class:`BackupRecord` rows.
    """
    query = db_session.query(BackupRecord)
    if status is not None:
        query = query.filter(BackupRecord.status == status)

    offset = (page - 1) * per_page
    rows = (
        query.order_by(BackupRecord.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def count_backup_records(
        *,
        db_session: DbSession,
        status: Optional[BackupStatus]
    ) -> int:
    """
        Count backup records, honoring an optional status filter.

        :param db_session: Active SQLAlchemy session.
        :param status: Optional status filter.

        :returns: The total record count.
    """
    query = db_session.query(BackupRecord)
    if status is not None:
        query = query.filter(BackupRecord.status == status)
    rtnval = int(query.count())
    return rtnval


def mark_backup_completed(
        *,
        db_session: DbSession,
        row: BackupRecord,
        archive_uri: str,
        archive_sha256: str,
        size_bytes: int,
        manifest: Dict[str, Any],
        completed_at: Any
    ) -> BackupRecord:
    """
        Transition a backup record to the ``completed`` state.

        :param db_session: Active SQLAlchemy session.
        :param row: The :class:`BackupRecord` to update.
        :param archive_uri: Backend-resolved archive location.
        :param archive_sha256: SHA-256 digest of the archive.
        :param size_bytes: Archive size in bytes.
        :param manifest: Substrate-inventory manifest.
        :param completed_at: Completion timestamp.

        :returns: The updated :class:`BackupRecord`.
    """
    row.status = BackupStatus.COMPLETED
    row.archive_uri = archive_uri
    row.archive_sha256 = archive_sha256
    row.size_bytes = size_bytes
    row.manifest = dict(manifest)
    row.completed_at = completed_at
    db_session.flush()
    rtnval = row
    return rtnval


def mark_backup_failed(
        *,
        db_session: DbSession,
        row: BackupRecord,
        error_detail: str,
        completed_at: Any
    ) -> BackupRecord:
    """
        Transition a backup record to the ``failed`` state.

        :param db_session: Active SQLAlchemy session.
        :param row: The :class:`BackupRecord` to update.
        :param error_detail: Failure explanation.
        :param completed_at: Failure timestamp.

        :returns: The updated :class:`BackupRecord`.
    """
    row.status = BackupStatus.FAILED
    row.error_detail = error_detail
    row.completed_at = completed_at
    db_session.flush()
    rtnval = row
    return rtnval
