"""
.. module:: backup.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Backup / disaster-recovery orchestrator facade.

.. moduleauthor:: Code Craft AI LLC

A backup captures everything needed to bring the service back on a
new host:

* the **database** -- a consistent snapshot (SQLite online backup API,
  or ``pg_dump`` for PostgreSQL; :mod:`backup.database_snapshot`);
* the **run artifacts** -- the artifact root
  (:mod:`jobs.results.artifact_root`);
* the **key material** the database is useless without -- KEK,
  password pepper and the other service keys
  (:mod:`backup.key_material`).

The database and artifacts go into one archive written through the
configured ``backup_storage_backend`` (``<id>.backup.tar.gz`` plus a
``.sha256`` sidecar, :mod:`backup.archive`); the keys go into a
separate key bundle in the key-bundle directory so the two can be kept
apart. The archive manifest records key fingerprints, never key bytes.

:func:`trigger_backup` is shared by ``POST /api/v1/backups`` and the
scheduled operator command (``python -m ccai.pychestrate.admin backup
create``). Every run is recorded in ``backup_record`` and committed as
it starts and as it ends, so a crash leaves a visible ``running`` row
rather than nothing.

Restore replaces the database, the artifacts and the keys the running
process has loaded, so it is an offline operation
(:func:`restore_backup`, driven by ``backup restore`` with the service
stopped). The running service can *verify* a backup end to end
(:func:`verify_backup` -- checksum, manifest, database integrity and
row counts, artifact count, key fingerprints, and that the KEK unwraps
the stored data keys) and hand back the exact restore command
(:func:`plan_restore`).

Caller-driven behavior follows the AGENTS.md "Aspects" pattern via
:class:`BackupAspects`; there are no behavior-modifying decorators.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import shlex
import shutil
import sqlite3
import tempfile

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.backup import repository
from ccai.pychestrate.webservice.backup.archive import (
    ARCHIVE_SUFFIX,
    ARTIFACTS_MEMBER_DIR,
    build_archive,
    extract_archive,
    read_archive_manifest,
    read_checksum_sidecar,
    write_checksum_sidecar,
)
from ccai.pychestrate.webservice.backup.database_snapshot import (
    CommandRunner,
    DIALECT_SQLITE,
    DatabaseRestoreResult,
    file_sha256,
    restore_database,
    snapshot_database,
    verify_database_snapshot,
)
from ccai.pychestrate.webservice.backup.errors import (
    BackupArchiveInvalidError,
    BackupBackendUnavailableError,
    BackupError,
    BackupRecordNotFoundError,
    BackupRequestInvalidError,
    BackupRestoreRequiresOfflineError,
)
from ccai.pychestrate.webservice.backup.events import BackupEventTopics
from ccai.pychestrate.webservice.backup.factories.local_backend import (
    LocalFilesystemBackupBackend,
)
from ccai.pychestrate.webservice.backup.key_material import (
    KEY_BUNDLE_SUFFIX,
    KeyRestoreOutcome,
    check_bundle_matches_manifest,
    collect_key_material,
    read_key_bundle,
    restore_key_material,
    write_key_bundle,
)
from ccai.pychestrate.webservice.backup.locations import (
    ensure_private_directory,
    resolve_backup_keys_dir,
    resolve_backup_root,
)
from ccai.pychestrate.webservice.backup.models import (
    BackupRecord,
    BackupStatus,
)


_LOGGER = logging.getLogger("pychestrate.backup.service")

#: The operator command that performs a restore (and a backup).
ADMIN_BACKUP_COMMAND: str = "python -m ccai.pychestrate.admin backup"

#: Stored data keys tried by the KEK check during verification.
KEK_CHECK_SAMPLE_SIZE: int = 20


@dataclass(frozen=True)
class BackupAspects:
    """
        Caller-controlled behavior knobs for a backup trigger.

        :param include_database: Snapshot the database.
        :param include_object_store: Archive the run-artifact tree.
        :param include_secrets: Write the key bundle (KEK, pepper, ...).
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


@dataclass(frozen=True)
class BackupSources:
    """
        Where a backup reads from and writes to. Resolved from the
        running configuration by :func:`resolve_backup_sources`; tests
        and the operator command build it explicitly.

        :ivar engine: SQLAlchemy engine of the database to snapshot.
        :ivar artifact_root: Run-artifact root.
        :ivar staging_root: Directory for work files (the backup root).
        :ivar keys_dir: Directory for key bundles.
        :ivar environ: Environment the key configuration is read from.
    """
    engine: Any
    artifact_root: str
    staging_root: str
    keys_dir: str
    environ: Mapping[str, str]


@dataclass(frozen=True)
class VerificationCheck:
    """
        One check of a backup verification.

        :ivar name: Short identifier (``archive.checksum``, ...).
        :ivar ok: Whether it passed.
        :ivar detail: Human-readable outcome.
    """
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VerificationReport:
    """
        Result of :func:`verify_backup`.

        :ivar archive_path: Archive verified.
        :ivar key_bundle_path: Key bundle verified, if any.
        :ivar manifest: Archive manifest (empty when unreadable).
        :ivar checks: Individual checks.
    """
    archive_path: str
    key_bundle_path: Optional[str]
    manifest: Dict[str, Any]
    checks: List[VerificationCheck]

    @property
    def ok(self) -> bool:
        """
            Whether every check passed.

            :returns: True when the backup is restorable.
        """
        rtnval = len(self.checks) > 0 and all(check.ok for check in self.checks)
        return rtnval

    def failures(self) -> List[VerificationCheck]:
        """
            The checks that failed.

            :returns: List of failed checks.
        """
        rtnval = [check for check in self.checks if check.ok is False]
        return rtnval


@dataclass(frozen=True)
class RestorePlan:
    """
        What restoring a recorded backup involves, for the REST layer.

        :ivar backup_id: The backup.
        :ivar archive_path: Local archive path, when the backend has one.
        :ivar key_bundle_path: Expected key bundle path, if the backup
                               has keys.
        :ivar restore_command: The operator command that restores it.
        :ivar verification: Verification report (dry runs).
    """
    backup_id: str
    archive_path: Optional[str]
    key_bundle_path: Optional[str]
    restore_command: str
    verification: Optional[VerificationReport]


@dataclass(frozen=True)
class RestoreReport:
    """
        Result of :func:`restore_backup`.

        :ivar backup_id: Backup restored.
        :ivar database: Database restore outcome, if restored.
        :ivar artifact_root: Artifact root restored, if restored.
        :ivar artifacts_previous_copy: Where the replaced artifact tree
                                       was kept.
        :ivar keys: Per-key outcomes.
    """
    backup_id: str
    database: Optional[DatabaseRestoreResult]
    artifact_root: Optional[str]
    artifacts_previous_copy: Optional[str]
    keys: List[KeyRestoreOutcome]


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _resolve_storage_backend() -> Any:
    """
        Resolve the active ``backup_storage_backend`` factory.

        The in-tree :class:`LocalFilesystemBackupBackend` is the bound
        implementation; a registry lookup replaces this when remote
        backends ship.

        :returns: A :class:`BackupStorageBackendProtocol` subclass.
    """
    rtnval: Any = LocalFilesystemBackupBackend
    return rtnval


def _engine_of(bind: Any) -> Any:
    """
        Return the :class:`Engine` behind a session bind (which may be
        a Connection).

        :param bind: ``db_session.get_bind()``.

        :returns: Engine.
    """
    rtnval = getattr(bind, "engine", bind)
    return rtnval


def resolve_backup_sources(*, engine: Any) -> BackupSources:
    """
        Resolve the backup sources from the running configuration.

        :param engine: Engine of the database to back up.

        :returns: :class:`BackupSources`.
    """
    from ccai.pychestrate.webservice.jobs.results.artifact_root import (
        resolve_artifact_root,
    )

    rtnval = BackupSources(
        engine=engine,
        artifact_root=resolve_artifact_root(),
        staging_root=resolve_backup_root(),
        keys_dir=resolve_backup_keys_dir(),
        environ=os.environ,
    )
    return rtnval


def key_bundle_path_for(*, keys_dir: str, backup_id: str) -> str:
    """
        Path of a backup's key bundle.

        :param keys_dir: Key-bundle directory.
        :param backup_id: Backup id.

        :returns: File path.
    """
    rtnval = os.path.join(keys_dir, backup_id + KEY_BUNDLE_SUFFIX)
    return rtnval


def build_restore_command(*, archive_path: str, key_bundle_path: Optional[str]) -> str:
    """
        The operator command that restores an archive.

        :param archive_path: Archive file.
        :param key_bundle_path: Key bundle, if the backup has one.

        :returns: Shell command line.
    """
    parts = [ADMIN_BACKUP_COMMAND, "restore", shlex.quote(archive_path)]
    if key_bundle_path is not None:
        parts.extend(["--keys", shlex.quote(key_bundle_path)])
    parts.append("--yes")
    rtnval = " ".join(parts)
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


def _count_secret_entries(db_session: DbSession) -> int:
    """
        Count stored secrets, for the manifest.

        :param db_session: Active SQLAlchemy session.

        :returns: Number of rows in ``phase1_secrets`` (0 when the table
                  is absent).
    """
    entry_count = 0
    try:
        from sqlalchemy import text as sa_text

        scalar = db_session.execute(sa_text("SELECT COUNT(*) FROM phase1_secrets")).scalar()
        if scalar is not None:
            entry_count = int(scalar)
    except Exception:
        db_session.rollback()
        entry_count = 0
    rtnval = entry_count
    return rtnval


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def trigger_backup(
        *,
        db_session: DbSession,
        aspects: Optional[BackupAspects] = None,
        actor_id: Optional[str] = None,
        sources: Optional[BackupSources] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> BackupRecordView:
    """
        Run a backup now.

        Snapshots the selected substrates, writes the archive through
        the configured ``backup_storage_backend`` and the key bundle to
        the key-bundle directory, and records the run in
        ``backup_record`` (committed at start and at end).

        :param db_session: Active SQLAlchemy session.
        :param aspects: Caller-controlled behavior knobs.
        :param actor_id: UUID of the triggering principal, if any.
        :param sources: Where to read / write; resolved from the
                        running configuration when omitted.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: The completed :class:`BackupRecordView`.
        :raises: BackupRequestInvalidError, BackupBackendUnavailableError,
                 BackupError subclasses for a failed substrate (the run
                 is recorded ``failed`` first).
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

    effective_sources = sources
    if effective_sources is None:
        effective_sources = resolve_backup_sources(engine=_engine_of(db_session.get_bind()))

    backend = _resolve_storage_backend()
    backend_kind = backend.backend_kind()

    row = repository.insert_backup_record(
        db_session=db_session,
        backend=backend_kind,
        note=effective_aspects.note,
        actor_id=actor_id,
    )
    db_session.commit()
    backup_id = str(row.backup_id)
    created_at = row.created_at if row.created_at is not None else utc_now()

    _LOGGER.info(
        "pychestrate.backup.run.started backup_id=%s backend=%s topic=%s",
        backup_id,
        backend_kind,
        BackupEventTopics.STARTED,
    )

    ensure_private_directory(path=effective_sources.staging_root)
    staging_dir = tempfile.mkdtemp(prefix=".staging-{}-".format(backup_id), dir=effective_sources.staging_root)
    key_bundle_path: Optional[str] = None
    try:
        keys = None
        if effective_aspects.include_secrets is True:
            # Read the keys first: a backup that cannot carry the KEK
            # fails before the expensive part.
            keys = collect_key_material(environ=effective_sources.environ)

        snapshot = None
        if effective_aspects.include_database is True:
            snapshot = snapshot_database(
                engine=effective_sources.engine,
                destination_dir=staging_dir,
                command_runner=command_runner,
            )

        manifest: Dict[str, Any] = {
            "backup_id": backup_id,
            "created_at": created_at.isoformat(),
            "note": effective_aspects.note,
        }
        if keys is not None:
            key_bundle_path = key_bundle_path_for(keys_dir=effective_sources.keys_dir, backup_id=backup_id)
            manifest["secrets"] = {
                "included": True,
                "entry_count": _count_secret_entries(db_session),
                "key_bundle": os.path.basename(key_bundle_path),
                "keys": [key.describe() for key in keys.keys],
                "skipped": dict(keys.skipped),
            }
        else:
            manifest["secrets"] = {"included": False}

        artifact_root = None
        if effective_aspects.include_object_store is True:
            artifact_root = effective_sources.artifact_root

        built = build_archive(
            destination_path=os.path.join(staging_dir, backup_id + ARCHIVE_SUFFIX),
            manifest=manifest,
            database_snapshot=snapshot,
            artifact_root=artifact_root,
        )

        if keys is not None:
            ensure_private_directory(path=effective_sources.keys_dir)
            write_key_bundle(
                keys=keys.keys,
                destination_path=key_bundle_path,
                backup_id=backup_id,
                created_at=created_at,
            )

        write_result = backend.store_archive_file(backup_id=backup_id, source_path=built.path)
        local_path = backend.local_archive_path(archive_uri=write_result.archive_uri)
        if local_path is not None:
            write_checksum_sidecar(archive_path=local_path, sha256=built.sha256)
    except Exception as xcpt:
        if key_bundle_path is not None and os.path.exists(key_bundle_path):
            os.remove(key_bundle_path)
        db_session.rollback()
        repository.mark_backup_failed(
            db_session=db_session,
            row=row,
            error_detail=str(xcpt),
            completed_at=utc_now(),
        )
        db_session.commit()
        _LOGGER.error(
            "pychestrate.backup.run.failed backup_id=%s cause=%s topic=%s",
            backup_id,
            str(xcpt).splitlines()[0] if len(str(xcpt)) > 0 else type(xcpt).__name__,
            BackupEventTopics.FAILED,
        )
        if isinstance(xcpt, BackupError):
            raise
        raise BackupBackendUnavailableError(
            "Backup {} failed: {}".format(backup_id, xcpt)
        ) from xcpt
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    repository.mark_backup_completed(
        db_session=db_session,
        row=row,
        archive_uri=write_result.archive_uri,
        archive_sha256=built.sha256,
        size_bytes=write_result.size_bytes,
        manifest=built.manifest,
        completed_at=utc_now(),
    )
    db_session.commit()

    _LOGGER.info(
        "pychestrate.backup.run.completed backup_id=%s bytes=%d archive=%s keys=%s topic=%s",
        backup_id,
        write_result.size_bytes,
        write_result.archive_uri,
        key_bundle_path,
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


def prune_backups(*, keep: int, backup_root: Optional[str] = None, keys_dir: Optional[str] = None) -> List[str]:
    """
        Delete all but the newest ``keep`` archives in the backup root,
        with their checksum sidecars and key bundles.

        :param keep: Number of archives to keep (>= 1).
        :param backup_root: Archive directory; defaults to the
                            configured backup root.
        :param keys_dir: Key-bundle directory; defaults to the
                         configured one.

        :returns: Paths removed.
    """
    if keep < 1:
        raise BackupRequestInvalidError("keep must be at least 1") from None
    root = backup_root if backup_root is not None else resolve_backup_root()
    bundles = keys_dir if keys_dir is not None else resolve_backup_keys_dir()
    if os.path.isdir(root) is False:
        return []

    archives = [
        os.path.join(root, name) for name in os.listdir(root) if name.endswith(ARCHIVE_SUFFIX)
    ]
    archives.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    removed: List[str] = []
    for archive_path in archives[keep:]:
        backup_id = os.path.basename(archive_path)[: -len(ARCHIVE_SUFFIX)]
        for path in (
                archive_path,
                archive_path + ".sha256",
                key_bundle_path_for(keys_dir=bundles, backup_id=backup_id),
            ):
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
    rtnval = removed
    return rtnval


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _work_parent(*, archive_path: str) -> str:
    """
        Pick the directory verification extracts into: next to the
        archive when writable (same volume, room for a large archive),
        else the system temporary directory (an archive on a read-only
        share).

        :param archive_path: Archive file.

        :returns: Directory path.
    """
    directory = os.path.dirname(os.path.abspath(archive_path))
    if os.access(directory, os.W_OK) is True:
        return directory
    rtnval = tempfile.gettempdir()
    return rtnval


def _check_kek_unwraps_stored_keys(*, sqlite_path: str, kek: bytes) -> VerificationCheck:
    """
        Try the bundle's KEK on the wrapped data keys stored in a SQLite
        snapshot. AES key wrap carries an integrity check, so a wrong
        KEK fails to unwrap.

        :param sqlite_path: Extracted snapshot.
        :param kek: KEK bytes from the key bundle.

        :returns: :class:`VerificationCheck`.
    """
    from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap

    try:
        connection = sqlite3.connect("file:{}?mode=ro".format(sqlite_path), uri=True)
        try:
            rows = connection.execute(
                "SELECT wrapped_dek FROM phase1_secret_versions"
                " WHERE wrapped_dek IS NOT NULL LIMIT ?",
                (KEK_CHECK_SAMPLE_SIZE,),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        rows = []
    if len(rows) == 0:
        rtnval = VerificationCheck(
            name="keys.kek_unwraps_data_keys",
            ok=True,
            detail="no stored secrets to check the KEK against",
        )
        return rtnval

    failures = 0
    for (wrapped,) in rows:
        try:
            aes_key_unwrap(kek, bytes(wrapped))
        except (InvalidUnwrap, ValueError):
            failures += 1
    rtnval = VerificationCheck(
        name="keys.kek_unwraps_data_keys",
        ok=failures == 0,
        detail=(
            "the KEK unwraps {} stored data key(s)".format(len(rows))
            if failures == 0
            else "the KEK failed to unwrap {} of {} stored data keys".format(failures, len(rows))
        ),
    )
    return rtnval


def verify_backup(
        *,
        archive_path: str,
        key_bundle_path: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> VerificationReport:
    """
        Verify that a backup can be restored, without touching the
        live system: checksum, manifest, database snapshot integrity
        and row counts, artifact count, key bundle fingerprints, and
        that the bundle's KEK unwraps the stored data keys.

        :param archive_path: Archive file.
        :param key_bundle_path: Key bundle, when the backup has one.
        :param expected_sha256: Recorded archive checksum; the
                                ``.sha256`` sidecar is used when omitted.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: :class:`VerificationReport`.
    """
    checks: List[VerificationCheck] = []
    manifest: Dict[str, Any] = {}

    if os.path.isfile(archive_path) is False:
        checks.append(VerificationCheck(name="archive.present", ok=False, detail="archive not found: " + archive_path))
        rtnval = VerificationReport(
            archive_path=archive_path, key_bundle_path=key_bundle_path, manifest=manifest, checks=checks,
        )
        return rtnval

    expected = expected_sha256 if expected_sha256 is not None else read_checksum_sidecar(archive_path=archive_path)
    if expected is None:
        checks.append(VerificationCheck(
            name="archive.checksum", ok=True, detail="no checksum recorded; integrity checked by extraction",
        ))
    else:
        actual = file_sha256(path=archive_path)
        checks.append(VerificationCheck(
            name="archive.checksum",
            ok=actual == str(expected).strip().lower(),
            detail="sha256 {}".format("matches" if actual == str(expected).strip().lower() else "does not match the recorded checksum"),
        ))

    work_dir = tempfile.mkdtemp(prefix=".verify-", dir=_work_parent(archive_path=archive_path))
    try:
        try:
            manifest = extract_archive(archive_path=archive_path, destination_dir=work_dir)
            checks.append(VerificationCheck(
                name="archive.manifest", ok=True,
                detail="format {} backup {}".format(manifest.get("format_version"), manifest.get("backup_id")),
            ))
        except BackupArchiveInvalidError as xcpt:
            checks.append(VerificationCheck(name="archive.manifest", ok=False, detail=str(xcpt).splitlines()[0]))
            rtnval = VerificationReport(
                archive_path=archive_path, key_bundle_path=key_bundle_path, manifest=manifest, checks=checks,
            )
            return rtnval

        database = manifest.get("database", {}) or {}
        snapshot_path: Optional[str] = None
        if database.get("included") is True:
            snapshot_path = os.path.join(work_dir, str(database.get("artifact")))
            if os.path.isfile(snapshot_path) is False:
                checks.append(VerificationCheck(name="database.present", ok=False, detail="snapshot missing from the archive"))
                snapshot_path = None
            else:
                matches = file_sha256(path=snapshot_path) == database.get("sha256")
                checks.append(VerificationCheck(
                    name="database.checksum", ok=matches,
                    detail="snapshot sha256 {}".format("matches the manifest" if matches else "differs from the manifest"),
                ))
                for snapshot_check in verify_database_snapshot(
                        snapshot_path=snapshot_path,
                        dialect=str(database.get("dialect")),
                        expected_row_counts=database.get("row_counts") or None,
                        command_runner=command_runner,
                    ):
                    checks.append(VerificationCheck(
                        name=snapshot_check.name, ok=snapshot_check.ok, detail=snapshot_check.detail,
                    ))

        object_store = manifest.get("object_store", {}) or {}
        if object_store.get("included") is True:
            artifacts_dir = os.path.join(work_dir, ARTIFACTS_MEMBER_DIR)
            found = 0
            for _, _, files in os.walk(artifacts_dir):
                found += len(files)
            expected_count = int(object_store.get("object_count", 0) or 0)
            checks.append(VerificationCheck(
                name="artifacts.count", ok=found == expected_count,
                detail="{} artifact file(s), manifest records {}".format(found, expected_count),
            ))

        secrets = manifest.get("secrets", {}) or {}
        if secrets.get("included") is True:
            if key_bundle_path is None or os.path.isfile(key_bundle_path) is False:
                checks.append(VerificationCheck(
                    name="keys.bundle", ok=False,
                    detail="key bundle {} not found; without it the backup's secrets cannot be decrypted".format(
                        key_bundle_path or secrets.get("key_bundle"),
                    ),
                ))
            else:
                try:
                    bundle = read_key_bundle(path=key_bundle_path)
                    mismatched = check_bundle_matches_manifest(bundle=bundle, manifest_keys=list(secrets.get("keys", [])))
                    checks.append(VerificationCheck(
                        name="keys.fingerprints", ok=len(mismatched) == 0,
                        detail=(
                            "{} key(s) match the archive".format(len(bundle.materials))
                            if len(mismatched) == 0
                            else "keys do not match the archive: {}".format(", ".join(mismatched))
                        ),
                    ))
                    kek = bundle.materials.get("kek", None)
                    if kek is not None and snapshot_path is not None and database.get("dialect") == DIALECT_SQLITE:
                        checks.append(_check_kek_unwraps_stored_keys(sqlite_path=snapshot_path, kek=kek))
                except BackupArchiveInvalidError as xcpt:
                    checks.append(VerificationCheck(name="keys.bundle", ok=False, detail=str(xcpt).splitlines()[0]))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    rtnval = VerificationReport(
        archive_path=archive_path, key_bundle_path=key_bundle_path, manifest=manifest, checks=checks,
    )
    _LOGGER.info(
        "pychestrate.backup.verify archive=%s ok=%s failed=%s topic=%s",
        archive_path,
        rtnval.ok,
        ",".join(check.name for check in rtnval.failures()),
        BackupEventTopics.RESTORE_VERIFIED,
    )
    return rtnval


def plan_restore(
        *,
        db_session: DbSession,
        backup_id: str,
        dry_run: bool,
        actor_id: Optional[str] = None,
        keys_dir: Optional[str] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> RestorePlan:
    """
        Handle a restore request made to the running service.

        A dry run verifies the backup end to end and returns the plan
        with the restore command. A real restore cannot run inside the
        service it replaces: it raises
        :class:`BackupRestoreRequiresOfflineError` carrying the command
        to run with the service stopped.

        :param db_session: Active SQLAlchemy session.
        :param backup_id: Backup record UUID.
        :param dry_run: Verify only.
        :param actor_id: Requesting principal, for the log.
        :param keys_dir: Key-bundle directory override.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: :class:`RestorePlan` (dry runs).
        :raises: BackupRecordNotFoundError, BackupRequestInvalidError
                 (backup did not complete / archive not local),
                 BackupRestoreRequiresOfflineError (real restore).
    """
    row = repository.find_backup_record_by_id(
        db_session=db_session,
        backup_id=backup_id,
    )
    if row is None:
        raise BackupRecordNotFoundError(
            "Backup record not found: {}".format(backup_id),
        )
    view = _row_to_view(row=row)
    if view.status != BackupStatus.COMPLETED.value:
        raise BackupRequestInvalidError(
            "Backup {} is {}; only a completed backup can be restored.".format(backup_id, view.status),
        )

    backend = _resolve_storage_backend()
    archive_path = backend.local_archive_path(archive_uri=view.archive_uri or "")
    key_bundle_path: Optional[str] = None
    if (view.manifest.get("secrets", {}) or {}).get("included") is True:
        key_bundle_path = key_bundle_path_for(
            keys_dir=keys_dir if keys_dir is not None else resolve_backup_keys_dir(),
            backup_id=backup_id,
        )
    shown_archive = archive_path if archive_path is not None else "<archive fetched from {}>".format(view.archive_uri)
    command = build_restore_command(archive_path=shown_archive, key_bundle_path=key_bundle_path)

    _LOGGER.info(
        "pychestrate.backup.restore.requested backup_id=%s actor=%s dry_run=%s topic=%s",
        backup_id,
        str(actor_id),
        dry_run,
        BackupEventTopics.RESTORE_REQUESTED,
    )

    if dry_run is False:
        err_lines = [
            "A restore replaces the database, the run artifacts and the keys this"
            " service has loaded, so it runs with the service stopped.",
        ]
        err_lines.append("Stop the service, then run: {}".format(command))
        raise BackupRestoreRequiresOfflineError(" ".join(err_lines), restore_command=command)

    if archive_path is None:
        raise BackupRequestInvalidError(
            "Archive {} is not on this host; fetch it and verify it with"
            " '{} verify <archive>'.".format(view.archive_uri, ADMIN_BACKUP_COMMAND),
        )

    report = verify_backup(
        archive_path=archive_path,
        key_bundle_path=key_bundle_path,
        expected_sha256=view.archive_sha256,
        command_runner=command_runner,
    )
    rtnval = RestorePlan(
        backup_id=backup_id,
        archive_path=archive_path,
        key_bundle_path=key_bundle_path,
        restore_command=command,
        verification=report,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Restore (offline)
# ---------------------------------------------------------------------------


def _replace_artifact_root(*, extracted_dir: str, artifact_root: str, now: datetime) -> Optional[str]:
    """
        Swap the extracted artifact tree into place, keeping the
        current tree as ``<root>.pre-restore-<timestamp>``.

        :param extracted_dir: ``artifacts`` directory from the archive
                              (may not exist when it held no files).
        :param artifact_root: Configured artifact root.
        :param now: Timestamp for the safety copy name.

        :returns: Where the previous tree was kept, if anything was.
    """
    previous_copy: Optional[str] = None
    parent = os.path.dirname(artifact_root)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    if os.path.exists(artifact_root):
        if len(os.listdir(artifact_root)) > 0:
            previous_copy = "{}.pre-restore-{}".format(artifact_root, now.strftime("%Y%m%dT%H%M%SZ"))
            os.replace(artifact_root, previous_copy)
        else:
            os.rmdir(artifact_root)
    if os.path.isdir(extracted_dir):
        shutil.move(extracted_dir, artifact_root)
    else:
        os.makedirs(artifact_root, mode=0o700, exist_ok=True)
    rtnval = previous_copy
    return rtnval


def _complete_own_record(
        *,
        database_url: Any,
        backup_id: str,
        archive_path: str,
        manifest: Dict[str, Any],
        completed_at: datetime
    ) -> bool:
    """
        The snapshot is taken after the run's ``backup_record`` row was
        committed as ``running``, so a restored database holds its own
        backup in that state. Mark it completed with the archive it was
        restored from.

        :param database_url: URL of the restored database.
        :param backup_id: The restored backup's id.
        :param archive_path: Archive restored from.
        :param manifest: Its manifest.
        :param completed_at: Timestamp to record.

        :returns: True when a row was updated.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    try:
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            row = repository.find_backup_record_by_id(db_session=session, backup_id=backup_id)
            if row is None or row.status != BackupStatus.RUNNING:
                return False
            repository.mark_backup_completed(
                db_session=session,
                row=row,
                archive_uri=LocalFilesystemBackupBackend.local_archive_uri(path=archive_path),
                archive_sha256=file_sha256(path=archive_path),
                size_bytes=os.path.getsize(archive_path),
                manifest=manifest,
                completed_at=completed_at,
            )
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()
    return True


def restore_backup(
        *,
        archive_path: str,
        key_bundle_path: Optional[str],
        database_url: Any,
        artifact_root: str,
        fallback_keys_dir: str,
        safety_copy_dir: str,
        overwrite_keys: bool = False,
        restore_keys: bool = True,
        restore_artifacts: bool = True,
        expected_sha256: Optional[str] = None,
        now: Optional[datetime] = None,
        environ: Optional[Mapping[str, str]] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> RestoreReport:
    """
        Restore a backup over the configured database, artifact root
        and key files. **The service must be stopped.**

        The backup is verified first and nothing is touched unless
        every check passes. Keys are restored first (a conflicting key
        file aborts before the database is replaced), then the
        database, then the artifacts. Everything replaced is kept
        (``pre-restore-<timestamp>``) until the operator removes it.

        :param archive_path: Archive file.
        :param key_bundle_path: Key bundle (required when the backup
                                has keys and ``restore_keys`` is set).
        :param database_url: URL of the database to replace.
        :param artifact_root: Artifact root to replace.
        :param fallback_keys_dir: Where keys go that the environment
                                  does not source from a file.
        :param safety_copy_dir: Where PostgreSQL's pre-restore dump and
                                work files go.
        :param overwrite_keys: Replace configured key files holding
                               different keys.
        :param restore_keys: Restore the key bundle.
        :param restore_artifacts: Restore the artifact tree.
        :param expected_sha256: Archive checksum override.
        :param now: Timestamp for safety-copy names.
        :param environ: Environment for key configuration.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: :class:`RestoreReport`.
        :raises: BackupArchiveInvalidError when verification fails;
                 BackupKeyMaterialError / BackupDatabaseError from the
                 restore steps.
    """
    stamp = now if now is not None else utc_now()
    report = verify_backup(
        archive_path=archive_path,
        key_bundle_path=key_bundle_path if restore_keys else None,
        expected_sha256=expected_sha256,
        command_runner=command_runner,
    )
    failures = report.failures()
    if restore_keys is False:
        failures = [check for check in failures if check.name != "keys.bundle"]
    if len(report.checks) == 0 or len(failures) > 0:
        err_lines = ["The backup failed verification; nothing was restored."]
        for check in failures:
            err_lines.append("{}: {}".format(check.name, check.detail))
        raise BackupArchiveInvalidError(os.linesep.join(err_lines)) from None
    manifest = report.manifest
    backup_id = str(manifest.get("backup_id"))

    ensure_private_directory(path=safety_copy_dir)
    work_dir = tempfile.mkdtemp(prefix=".restore-", dir=safety_copy_dir)
    try:
        extract_archive(archive_path=archive_path, destination_dir=work_dir)

        key_outcomes: List[KeyRestoreOutcome] = []
        if restore_keys is True and (manifest.get("secrets", {}) or {}).get("included") is True:
            key_outcomes = restore_key_material(
                bundle=read_key_bundle(path=key_bundle_path),
                fallback_dir=fallback_keys_dir,
                overwrite=overwrite_keys,
                now=stamp,
                environ=environ,
            )

        database_result: Optional[DatabaseRestoreResult] = None
        database = manifest.get("database", {}) or {}
        if database.get("included") is True:
            database_result = restore_database(
                database_url=database_url,
                snapshot_path=os.path.join(work_dir, str(database.get("artifact"))),
                dialect=str(database.get("dialect")),
                safety_copy_dir=safety_copy_dir,
                now=stamp,
                command_runner=command_runner,
            )
            _complete_own_record(
                database_url=database_url,
                backup_id=backup_id,
                archive_path=archive_path,
                manifest=manifest,
                completed_at=stamp,
            )

        restored_root: Optional[str] = None
        artifacts_previous: Optional[str] = None
        if restore_artifacts is True and (manifest.get("object_store", {}) or {}).get("included") is True:
            artifacts_previous = _replace_artifact_root(
                extracted_dir=os.path.join(work_dir, ARTIFACTS_MEMBER_DIR),
                artifact_root=artifact_root,
                now=stamp,
            )
            restored_root = artifact_root
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    _LOGGER.info(
        "pychestrate.backup.restore.completed backup_id=%s archive=%s topic=%s",
        backup_id,
        archive_path,
        BackupEventTopics.RESTORE_COMPLETED,
    )
    rtnval = RestoreReport(
        backup_id=backup_id,
        database=database_result,
        artifact_root=restored_root,
        artifacts_previous_copy=artifacts_previous,
        keys=key_outcomes,
    )
    return rtnval


def read_manifest(*, archive_path: str) -> Dict[str, Any]:
    """
        Read an archive's manifest (for listings).

        :param archive_path: Archive file.

        :returns: Parsed manifest.
    """
    rtnval = read_archive_manifest(archive_path=archive_path)
    return rtnval
