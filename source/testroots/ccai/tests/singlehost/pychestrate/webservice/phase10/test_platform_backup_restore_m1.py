"""
.. module:: test_platform_backup_restore_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for real backups and a working restore
               (audit ORG-F04).

.. moduleauthor:: Code Craft AI LLC

Before ORG-F04 a "backup" was a tar holding a JSON list of table
names and the restore route answered 501; losing the host lost the
database and the KEK that decrypts every stored secret. These tests
pin the replacement:

* the archive carries a consistent snapshot of the database rows,
  the run-artifact tree, and a manifest whose checksums match;
* the key bundle is written separately (0600) with the KEK and the
  pepper, and the archive holds no key bytes;
* the backup record is committed (completed / failed);
* verification catches a tampered archive, a mismatched key bundle,
  and a KEK that does not unwrap the stored data keys;
* a backup -> wipe -> restore round trip brings the rows, the
  artifacts and the key files back, and marks the backup's own record
  completed;
* restore refuses to replace a different existing key unless asked,
  and changes nothing when verification fails;
* PostgreSQL goes through pg_dump / pg_restore with the password in
  PGPASSWORD, never on the command line;
* pruning keeps the newest archives with their key bundles;
* the operator command refuses a restore without --yes;
* the service asked to restore itself answers with the offline
  command; a dry run verifies;
* the deploy installs a daily backup timer.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time

from typing import Any, Dict, List

from cryptography.hazmat.primitives.keywrap import aes_key_wrap
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.backup import cli as backup_cli
from ccai.pychestrate.webservice.backup import database_snapshot
from ccai.pychestrate.webservice.backup import service as backup_service
from ccai.pychestrate.webservice.backup.errors import (
    BackupArchiveInvalidError,
    BackupKeyMaterialError,
    BackupRestoreRequiresOfflineError,
)
from ccai.pychestrate.webservice.backup.models import BackupRecord, BackupStatus
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretVersion,
    SecretVersionState,
)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class _Host:
    """
        A throwaway "host": SQLite database with the backup and secrets
        tables, one stored secret whose data key is wrapped under the
        KEK, KEK + pepper files, and one run artifact.
    """

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="orgf04-")
        self.presence = os.path.join(self.root, "presence")
        os.makedirs(self.presence)
        self.db_path = os.path.join(self.presence, "pychestrate.sqlite")
        self.database_url = "sqlite:///" + self.db_path
        self.artifact_root = os.path.join(self.presence, "artifacts")
        self.backup_root = os.path.join(self.presence, "backups")
        self.keys_dir = os.path.join(self.presence, "backup-keys")
        self.secrets_dir = os.path.join(self.root, "dev-secrets")
        os.makedirs(self.secrets_dir)
        self.kek = os.urandom(32)
        self.pepper = os.urandom(32)
        self.kek_path = os.path.join(self.secrets_dir, "dev.kek")
        self.pepper_path = os.path.join(self.secrets_dir, "dev.password-pepper")
        _write(self.kek_path, self.kek)
        _write(self.pepper_path, self.pepper)
        self.environ: Dict[str, str] = {
            "PYCHESTRATE_KEK_SOURCE": "file",
            "PYCHESTRATE_KEK_ID": "kek-1",
            "PYCHESTRATE_KEK_FILE_PATH": self.kek_path,
            "PYCHESTRATE_PASSWORD_PEPPER_SOURCE": "file",
            "PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH": self.pepper_path,
        }
        self.artifact_relative = os.path.join("proj", "results", "2026", "09", "22", "rpa", "run-1", "out.log")
        _write(os.path.join(self.artifact_root, self.artifact_relative), b"artifact-bytes")

        self.engine = create_engine(self.database_url)
        PychestratePhase1Base.metadata.create_all(
            self.engine,
            tables=[BackupRecord.__table__, SecretRecord.__table__, SecretVersion.__table__],
        )
        session = sessionmaker(bind=self.engine)()
        session.add(SecretRecord(secret_ref="db/password", backend_name="local"))
        session.flush()
        session.add(SecretVersion(
            version_id=new_uuid(),
            secret_ref="db/password",
            version_number=1,
            state=SecretVersionState.ACTIVE,
            wrapped_dek=aes_key_wrap(self.kek, os.urandom(32)),
            kek_id="kek-1",
        ))
        session.commit()
        session.close()
        return

    def sources(self) -> backup_service.BackupSources:
        rtnval = backup_service.BackupSources(
            engine=self.engine,
            artifact_root=self.artifact_root,
            staging_root=self.backup_root,
            keys_dir=self.keys_dir,
            environ=self.environ,
        )
        return rtnval

    def backup(self, **aspects: Any) -> backup_service.BackupRecordView:
        session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        previous = {
            name: os.environ.get(name, None)
            for name in ("PYCHESTRATE_BACKUP_ROOT", "PYCHESTRATE_BACKUP_KEYS_DIR")
        }
        os.environ["PYCHESTRATE_BACKUP_ROOT"] = self.backup_root
        os.environ["PYCHESTRATE_BACKUP_KEYS_DIR"] = self.keys_dir
        try:
            rtnval = backup_service.trigger_backup(
                db_session=session,
                aspects=backup_service.BackupAspects(**aspects),
                sources=self.sources(),
            )
        finally:
            session.close()
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        return rtnval

    def archive_path(self, view: backup_service.BackupRecordView) -> str:
        rtnval = view.archive_uri[len("file://"):]
        return rtnval

    def bundle_path(self, view: backup_service.BackupRecordView) -> str:
        rtnval = os.path.join(self.keys_dir, view.backup_id + ".keys.tar")
        return rtnval

    def restore(self, view: backup_service.BackupRecordView, **options: Any) -> backup_service.RestoreReport:
        self.engine.dispose()
        kwargs: Dict[str, Any] = {
            "archive_path": self.archive_path(view),
            "key_bundle_path": self.bundle_path(view),
            "database_url": self.database_url,
            "artifact_root": self.artifact_root,
            "fallback_keys_dir": os.path.join(self.root, "restored-keys"),
            "safety_copy_dir": self.backup_root,
            "environ": self.environ,
        }
        kwargs.update(options)
        rtnval = backup_service.restore_backup(**kwargs)
        return rtnval

    def wipe(self) -> None:
        self.engine.dispose()
        os.remove(self.db_path)
        shutil.rmtree(self.artifact_root)
        os.remove(self.kek_path)
        os.remove(self.pepper_path)
        return

    def close(self) -> None:
        self.engine.dispose()
        shutil.rmtree(self.root, ignore_errors=True)
        return


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return


def _read(path: str) -> bytes:
    with open(path, "rb") as handle:
        rtnval = handle.read()
    return rtnval


def _archive_members(path: str) -> Dict[str, bytes]:
    members: Dict[str, bytes] = {}
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive:
            if member.isfile():
                members[member.name] = archive.extractfile(member).read()
    return members


# ---------------------------------------------------------------------------
# Backup contents
# ---------------------------------------------------------------------------


def test_archive_holds_a_snapshot_with_the_database_rows():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the archive's database member is a SQLite snapshot that
    contains the rows committed before the backup.**
    """
    host = _Host()
    try:
        view = host.backup()
        snapshot = _archive_members(host.archive_path(view))["database/pychestrate.sqlite"]
        copy = os.path.join(host.root, "copy.sqlite")
        _write(copy, snapshot)
        connection = sqlite3.connect(copy)
        refs = [row[0] for row in connection.execute("SELECT secret_ref FROM phase1_secrets")]
        connection.close()
    finally:
        host.close()
    testbase.assert_equal(refs, ["db/password"])
    return


def test_manifest_checksum_matches_the_database_member():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the manifest records the SHA-256 of the database member
    it sits next to.**
    """
    import hashlib
    import json

    host = _Host()
    try:
        view = host.backup()
        members = _archive_members(host.archive_path(view))
        manifest = json.loads(members["manifest.json"].decode("utf-8"))
        actual = hashlib.sha256(members["database/pychestrate.sqlite"]).hexdigest()
    finally:
        host.close()
    testbase.assert_equal(manifest["database"]["sha256"], actual)
    return


def test_archive_holds_the_run_artifacts():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: every file under the artifact root is in the archive
    below artifacts/.**
    """
    host = _Host()
    try:
        view = host.backup()
        members = _archive_members(host.archive_path(view))
        stored = members.get("artifacts/" + host.artifact_relative.replace(os.sep, "/"))
    finally:
        host.close()
    testbase.assert_equal(stored, b"artifact-bytes")
    return


def test_key_bundle_holds_the_kek_and_the_pepper():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the key bundle carries the KEK and the pepper bytes.**
    """
    from ccai.pychestrate.webservice.backup.key_material import read_key_bundle

    host = _Host()
    try:
        view = host.backup()
        bundle = read_key_bundle(path=host.bundle_path(view))
        materials = (bundle.materials["kek"], bundle.materials["password_pepper"])
        expected = (host.kek, host.pepper)
    finally:
        host.close()
    testbase.assert_equal(materials == expected, True)
    return


def test_key_bundle_is_private_to_the_service_user():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the key bundle is written mode 0600.**
    """
    host = _Host()
    try:
        view = host.backup()
        mode = os.stat(host.bundle_path(view)).st_mode & 0o777
    finally:
        host.close()
    testbase.assert_equal(oct(mode), oct(0o600))
    return


def test_archive_contains_no_key_bytes():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: neither the KEK nor the pepper appears anywhere in the
    data archive -- only in the separate key bundle.**
    """
    host = _Host()
    try:
        view = host.backup()
        blob = b"".join(_archive_members(host.archive_path(view)).values())
        leaked = host.kek in blob or host.pepper in blob
    finally:
        host.close()
    testbase.assert_equal(leaked, False)
    return


def test_backup_record_is_committed_as_completed():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: a new session sees the run's backup_record row as
    completed with the archive checksum (the old service never
    committed it).**
    """
    host = _Host()
    try:
        view = host.backup()
        session = sessionmaker(bind=host.engine)()
        row = session.query(BackupRecord).filter(BackupRecord.backup_id == view.backup_id).first()
        found = (row.status, row.archive_sha256)
        session.close()
    finally:
        host.close()
    testbase.assert_equal(found, (BackupStatus.COMPLETED, view.archive_sha256))
    return


def test_backup_without_a_readable_kek_is_recorded_failed():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: when the KEK file cannot be read the run fails, is
    recorded failed, and leaves no archive behind.**
    """
    host = _Host()
    try:
        os.remove(host.kek_path)
        raised = False
        try:
            host.backup()
        except BackupKeyMaterialError:
            raised = True
        session = sessionmaker(bind=host.engine)()
        statuses = [row.status for row in session.query(BackupRecord).all()]
        session.close()
        leftovers = [
            name for name in os.listdir(host.backup_root) if name.endswith(".backup.tar.gz")
        ]
    finally:
        host.close()
    testbase.assert_equal((raised, statuses, leftovers), (True, [BackupStatus.FAILED], []))
    return


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_verification_passes_for_a_fresh_backup():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: every verification check passes for an untouched
    archive + key bundle, including the KEK unwrapping the stored
    data key.**
    """
    host = _Host()
    try:
        view = host.backup()
        report = backup_service.verify_backup(
            archive_path=host.archive_path(view), key_bundle_path=host.bundle_path(view),
        )
        names = [check.name for check in report.checks]
    finally:
        host.close()
    testbase.assert_equal((report.ok, "keys.kek_unwraps_data_keys" in names), (True, True))
    return


def test_verification_detects_a_tampered_archive():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: an archive whose bytes changed after the backup fails
    the checksum check (sha256 sidecar).**
    """
    host = _Host()
    try:
        view = host.backup()
        path = host.archive_path(view)
        with open(path, "ab") as handle:
            handle.write(b"tamper")
        report = backup_service.verify_backup(archive_path=path, key_bundle_path=host.bundle_path(view))
        failed = [check.name for check in report.failures()]
    finally:
        host.close()
    testbase.assert_true("archive.checksum" in failed)
    return


def test_verification_rejects_the_key_bundle_of_another_backup():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: pairing an archive with a key bundle holding different
    keys fails the fingerprint check.**
    """
    host = _Host()
    other = _Host()
    try:
        view = host.backup()
        other_view = other.backup()
        report = backup_service.verify_backup(
            archive_path=host.archive_path(view), key_bundle_path=other.bundle_path(other_view),
        )
        failed = [check.name for check in report.failures()]
    finally:
        host.close()
        other.close()
    testbase.assert_true("keys.fingerprints" in failed)
    return


def test_kek_check_fails_for_a_kek_that_did_not_wrap_the_data_keys():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the KEK check fails when the KEK cannot unwrap the data
    keys stored in the snapshot.**
    """
    host = _Host()
    try:
        view = host.backup()
        members = _archive_members(host.archive_path(view))
        snapshot = os.path.join(host.root, "snap.sqlite")
        _write(snapshot, members["database/pychestrate.sqlite"])
        check = backup_service._check_kek_unwraps_stored_keys(sqlite_path=snapshot, kek=os.urandom(32))
    finally:
        host.close()
    testbase.assert_equal(check.ok, False)
    return


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def test_restore_after_wipe_brings_the_database_rows_back():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: backup -> delete database, artifacts and keys ->
    restore -> the stored secret row is back.**
    """
    host = _Host()
    try:
        view = host.backup()
        host.wipe()
        host.restore(view)
        connection = sqlite3.connect(host.db_path)
        refs = [row[0] for row in connection.execute("SELECT secret_ref FROM phase1_secrets")]
        connection.close()
    finally:
        host.close()
    testbase.assert_equal(refs, ["db/password"])
    return


def test_restore_after_wipe_brings_the_artifacts_back():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the run artifact is back under the artifact root after
    the round trip.**
    """
    host = _Host()
    try:
        view = host.backup()
        host.wipe()
        host.restore(view)
        restored = _read(os.path.join(host.artifact_root, host.artifact_relative))
    finally:
        host.close()
    testbase.assert_equal(restored, b"artifact-bytes")
    return


def test_restore_after_wipe_puts_the_keys_back_where_they_are_loaded_from():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the KEK and pepper are written back to their configured
    file paths, mode 0600.**
    """
    host = _Host()
    try:
        view = host.backup()
        host.wipe()
        host.restore(view)
        found = (
            _read(host.kek_path) == host.kek,
            _read(host.pepper_path) == host.pepper,
            oct(os.stat(host.kek_path).st_mode & 0o777),
        )
    finally:
        host.close()
    testbase.assert_equal(found, (True, True, oct(0o600)))
    return


def test_restore_marks_the_backups_own_record_completed():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the snapshot was taken while its own record was
    "running"; after restore that record reads completed.**
    """
    import uuid

    host = _Host()
    try:
        view = host.backup()
        host.wipe()
        host.restore(view)
        connection = sqlite3.connect(host.db_path)
        # UUIDType(binary=False) stores the 32-character hex form.
        status = connection.execute(
            "SELECT status FROM backup_record WHERE backup_id = ?", (uuid.UUID(view.backup_id).hex,),
        ).fetchone()[0]
        connection.close()
    finally:
        host.close()
    testbase.assert_equal(status, "COMPLETED")
    return


def test_restore_keeps_the_replaced_database():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: restoring over an existing database keeps the old file
    in a pre-restore directory next to it.**
    """
    host = _Host()
    try:
        view = host.backup()
        report = host.restore(view)
        kept = os.path.isfile(os.path.join(report.database.previous_copy, "pychestrate.sqlite"))
    finally:
        host.close()
    testbase.assert_equal(kept, True)
    return


def test_restore_refuses_to_replace_a_different_key_without_overwrite():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: when the configured KEK file holds a different key the
    restore stops before touching the database, unless
    overwrite_keys is set.**
    """
    host = _Host()
    try:
        view = host.backup()
        _write(host.kek_path, os.urandom(32))
        before = os.path.getmtime(host.db_path)
        time.sleep(0.01)
        raised = False
        try:
            host.restore(view)
        except BackupKeyMaterialError:
            raised = True
        untouched = os.path.getmtime(host.db_path) == before
    finally:
        host.close()
    testbase.assert_equal((raised, untouched), (True, True))
    return


def test_restore_with_overwrite_keys_replaces_a_different_key():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: with overwrite_keys the backed-up KEK replaces a
    different configured key, which is kept as a pre-restore copy.**
    """
    host = _Host()
    try:
        view = host.backup()
        _write(host.kek_path, os.urandom(32))
        report = host.restore(view, overwrite_keys=True)
        kek_outcome = [outcome for outcome in report.keys if outcome.name == "kek"][0]
        found = (_read(host.kek_path) == host.kek, kek_outcome.action, os.path.isfile(kek_outcome.previous_copy))
    finally:
        host.close()
    testbase.assert_equal(found, (True, "replaced", True))
    return


def test_restore_changes_nothing_when_verification_fails():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: a tampered archive is refused before any file is
    touched.**
    """
    host = _Host()
    try:
        view = host.backup()
        with open(host.archive_path(view), "ab") as handle:
            handle.write(b"tamper")
        host.wipe()
        raised = False
        try:
            host.restore(view)
        except BackupArchiveInvalidError:
            raised = True
        nothing_written = os.path.exists(host.db_path) is False and os.path.exists(host.kek_path) is False
    finally:
        host.close()
    testbase.assert_equal((raised, nothing_written), (True, True))
    return


# ---------------------------------------------------------------------------
# PostgreSQL tooling
# ---------------------------------------------------------------------------


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def __call__(self, argv: List[str], extra_env: Dict[str, str]) -> database_snapshot.CommandResult:
        self.calls.append((list(argv), dict(extra_env)))
        if "--file" in argv:
            _write(argv[argv.index("--file") + 1], b"PGDMP")
        rtnval = database_snapshot.CommandResult(returncode=0, stdout="", stderr="")
        return rtnval


def _with_fake_pg_tools(action: Any) -> Any:
    previous = {
        name: os.environ.get(name, None)
        for name in (database_snapshot.ENV_PG_DUMP_PATH, database_snapshot.ENV_PG_RESTORE_PATH)
    }
    os.environ[database_snapshot.ENV_PG_DUMP_PATH] = "/usr/bin/pg_dump"
    os.environ[database_snapshot.ENV_PG_RESTORE_PATH] = "/usr/bin/pg_restore"
    try:
        rtnval = action()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return rtnval


_PG_URL = "postgresql+psycopg2://pych:s3cr3t-pw@db.internal:5433/pychestrate?sslmode=require"


def test_pg_dump_gets_the_password_through_the_environment_only():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: pg_dump runs in custom format with the password in
    PGPASSWORD and nowhere on its command line.**
    """
    runner = _RecordingRunner()
    work = tempfile.mkdtemp(prefix="orgf04-pg-")
    try:
        _with_fake_pg_tools(lambda: database_snapshot.dump_postgres(
            database_url=_PG_URL, destination=os.path.join(work, "x.pgdump"), command_runner=runner,
        ))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    argv, extra_env = runner.calls[0]
    testbase.assert_equal(
        ("--format=custom" in argv, extra_env.get("PGPASSWORD"), any("s3cr3t-pw" in arg for arg in argv)),
        (True, "s3cr3t-pw", False),
    )
    return


def test_pg_connection_string_carries_host_port_user_database_and_options():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the libpq connection string keeps every URL part except
    the password (host, port, user, dbname, sslmode).**
    """
    conninfo, _ = database_snapshot.postgres_connection_arguments(database_url=_PG_URL)
    testbase.assert_equal(
        conninfo,
        "host='db.internal' port='5433' user='pych' dbname='pychestrate' sslmode='require'",
    )
    return


def test_pg_restore_runs_clean_in_a_single_transaction_after_a_safety_dump():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: a PostgreSQL restore first dumps the current database,
    then runs pg_restore --clean --if-exists --single-transaction
    --exit-on-error.**
    """
    runner = _RecordingRunner()
    work = tempfile.mkdtemp(prefix="orgf04-pg-")
    try:
        _with_fake_pg_tools(lambda: database_snapshot.restore_database(
            database_url=_PG_URL,
            snapshot_path=os.path.join(work, "backup.pgdump"),
            dialect=database_snapshot.DIALECT_POSTGRESQL,
            safety_copy_dir=work,
            command_runner=runner,
        ))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    tools = [os.path.basename(argv[0]) for argv, _ in runner.calls]
    restore_argv = runner.calls[-1][0]
    flags = {"--clean", "--if-exists", "--single-transaction", "--exit-on-error"}
    testbase.assert_equal((tools, flags.issubset(set(restore_argv))), (["pg_dump", "pg_restore"], True))
    return


def test_restore_refuses_a_backup_of_another_database_dialect():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: a SQLite snapshot is not restored over a PostgreSQL
    database (or vice versa).**
    """
    from ccai.pychestrate.webservice.backup.errors import BackupDatabaseError

    raised = False
    try:
        database_snapshot.restore_database(
            database_url=_PG_URL,
            snapshot_path="/nonexistent.sqlite",
            dialect=database_snapshot.DIALECT_SQLITE,
        )
    except BackupDatabaseError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Retention, operator command, REST plan
# ---------------------------------------------------------------------------


def test_prune_keeps_the_newest_archives_with_their_key_bundles():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: prune_backups(keep=1) removes the older archive, its
    checksum sidecar and its key bundle, and keeps the newest set.**
    """
    host = _Host()
    try:
        first = host.backup()
        old_time = time.time() - 3600
        os.utime(host.archive_path(first), (old_time, old_time))
        second = host.backup()
        backup_service.prune_backups(keep=1, backup_root=host.backup_root, keys_dir=host.keys_dir)
        state = (
            os.path.exists(host.archive_path(first)),
            os.path.exists(host.bundle_path(first)),
            os.path.exists(host.archive_path(second)),
            os.path.exists(host.bundle_path(second)),
        )
    finally:
        host.close()
    testbase.assert_equal(state, (False, False, True, True))
    return


def test_operator_restore_requires_confirmation():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: "backup restore" without --yes exits 2 and restores
    nothing.**
    """
    out = io.StringIO()
    err = io.StringIO()
    code = backup_cli.main(argv=["restore", "/nonexistent.backup.tar.gz"], out=out, err=err)
    testbase.assert_equal((code, "--yes" in err.getvalue()), (backup_cli.EXIT_USAGE, True))
    return


def test_admin_dispatcher_routes_the_backup_subsystem():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: "pychestrate-admin backup --help" reaches the backup
    command (exit 0) instead of "unknown subsystem".**
    """
    from ccai.pychestrate.admin import __main__ as admin_main

    code = admin_main.main(argv=["backup", "--help"])
    testbase.assert_equal(code, 0)
    return


def test_service_answers_a_restore_request_with_the_offline_command():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: plan_restore without dry_run raises
    BackupRestoreRequiresOfflineError whose command names the archive
    and the key bundle.**
    """
    host = _Host()
    try:
        view = host.backup()
        session = sessionmaker(bind=host.engine)()
        command = ""
        try:
            backup_service.plan_restore(
                db_session=session, backup_id=view.backup_id, dry_run=False, keys_dir=host.keys_dir,
            )
        except BackupRestoreRequiresOfflineError as xcpt:
            command = xcpt.restore_command
        session.close()
        expected_parts = (host.archive_path(view) in command, host.bundle_path(view) in command)
    finally:
        host.close()
    testbase.assert_equal(expected_parts, (True, True))
    return


def test_service_dry_run_verifies_a_recorded_backup():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: plan_restore with dry_run returns a passing verification
    report for a recorded backup.**
    """
    host = _Host()
    try:
        view = host.backup()
        session = sessionmaker(bind=host.engine)()
        plan = backup_service.plan_restore(
            db_session=session, backup_id=view.backup_id, dry_run=True, keys_dir=host.keys_dir,
        )
        session.close()
    finally:
        host.close()
    testbase.assert_equal(plan.verification.ok, True)
    return


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..")
    )
    return rtnval


def test_deploy_installs_a_daily_backup_timer():
    """
    **Feature: backup and restore (ORG-F04)**
    **Property: the deploy installs and enables pychestrate-backup.timer,
    whose unit runs "backup create".**
    """
    root = _repo_root()
    with open(os.path.join(root, "deployment", "deploy-alpha-to-host.sh"), "r", encoding="utf-8") as handle:
        script = handle.read()
    with open(os.path.join(root, "deployment", "pychestrate-backup.service.template"), "r", encoding="utf-8") as handle:
        unit = handle.read()
    with open(os.path.join(root, "deployment", "pychestrate-backup.timer.template"), "r", encoding="utf-8") as handle:
        timer = handle.read()
    testbase.assert_equal(
        (
            "systemctl enable --now pychestrate-backup.timer" in script,
            "admin backup create" in unit,
            "OnCalendar=" in timer,
        ),
        (True, True, True),
    )
    return
