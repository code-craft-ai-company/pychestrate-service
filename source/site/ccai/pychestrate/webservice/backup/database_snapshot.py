"""
.. module:: backup.database_snapshot
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Consistent database snapshots and restores, per dialect.

.. moduleauthor:: Code Craft AI LLC

Each supported database is backed up and restored with its native,
consistent mechanism:

* **SQLite** -- the SQLite online backup API
  (:meth:`sqlite3.Connection.backup`) copies the live database page
  by page under a read lock, so the snapshot is transactionally
  consistent even while the service keeps writing. Restore swaps the
  snapshot into place atomically (``os.replace``) after moving the
  current file and any ``-journal`` / ``-wal`` / ``-shm`` sidecars
  aside -- a leftover hot journal would otherwise be replayed into
  the restored file.
* **PostgreSQL** -- ``pg_dump --format=custom`` and
  ``pg_restore --clean --if-exists --single-transaction``. The
  password travels in ``PGPASSWORD``, never on the command line
  (visible in ``ps``); every other URL parameter is passed as a libpq
  connection string. Restore first dumps the current database next to
  the backups as a safety copy.

Any other dialect is refused with :class:`BackupDatabaseError`.

The command runner is injectable so the PostgreSQL path can be
exercised without a server.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.engine import URL, make_url

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.backup.errors import BackupDatabaseError


_LOGGER = logging.getLogger("pychestrate.backup.database")


DIALECT_SQLITE: str = "sqlite"
DIALECT_POSTGRESQL: str = "postgresql"

#: File name of the database member inside an archive, per dialect.
SNAPSHOT_FILE_NAMES: Dict[str, str] = {
    DIALECT_SQLITE: "pychestrate.sqlite",
    DIALECT_POSTGRESQL: "pychestrate.pgdump",
}

#: Environment overrides for the PostgreSQL client tools; default is
#: whatever ``pg_dump`` / ``pg_restore`` is first on ``PATH``.
ENV_PG_DUMP_PATH: str = "PYCHESTRATE_PG_DUMP_PATH"
ENV_PG_RESTORE_PATH: str = "PYCHESTRATE_PG_RESTORE_PATH"

#: Upper bound on a single ``pg_dump`` / ``pg_restore`` run.
PG_TOOL_TIMEOUT_SECONDS: int = 6 * 60 * 60

#: SQLite files that belong to a database besides the main file.
SQLITE_SIDECAR_SUFFIXES: Tuple[str, ...] = ("-journal", "-wal", "-shm")

_HASH_CHUNK_BYTES: int = 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    """
        Outcome of an external tool run.

        :ivar returncode: Process exit status.
        :ivar stdout: Captured standard output.
        :ivar stderr: Captured standard error.
    """
    returncode: int
    stdout: str
    stderr: str


#: ``(argv, extra_env) -> CommandResult``.
CommandRunner = Callable[[List[str], Dict[str, str]], CommandResult]


@dataclass(frozen=True)
class DatabaseSnapshot:
    """
        A database snapshot written to a local file.

        :ivar dialect: ``sqlite`` or ``postgresql``.
        :ivar file_path: Absolute path of the snapshot file.
        :ivar file_name: Member name used inside the archive.
        :ivar size_bytes: Snapshot size.
        :ivar sha256: Hex SHA-256 of the snapshot file.
        :ivar table_count: Number of tables captured.
        :ivar alembic_revision: Schema revision, when the database is
                                alembic-managed.
        :ivar row_counts: Rows per table (SQLite only).
    """
    dialect: str
    file_path: str
    file_name: str
    size_bytes: int
    sha256: str
    table_count: int
    alembic_revision: Optional[str]
    row_counts: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DatabaseRestoreResult:
    """
        What a restore replaced.

        :ivar dialect: ``sqlite`` or ``postgresql``.
        :ivar target: The database file (SQLite) or database name
                      (PostgreSQL) that now holds the backup.
        :ivar previous_copy: Where the pre-restore state was kept
                             (directory or dump file), or ``None``
                             when there was nothing to keep.
    """
    dialect: str
    target: str
    previous_copy: Optional[str]


@dataclass(frozen=True)
class SnapshotCheck:
    """
        One verification check on a snapshot.

        :ivar name: Short check identifier.
        :ivar ok: Whether the check passed.
        :ivar detail: Human-readable outcome.
    """
    name: str
    ok: bool
    detail: str


def default_command_runner(argv: List[str], extra_env: Dict[str, str]) -> CommandResult:
    """
        Run an external tool with ``extra_env`` merged over the
        process environment and capture its output.

        :param argv: Command line.
        :param extra_env: Variables added to the environment.

        :returns: :class:`CommandResult`.
    """
    env = dict(os.environ)
    env.update(extra_env)
    completed = subprocess.run(
        argv,
        env=env,
        capture_output=True,
        text=True,
        timeout=PG_TOOL_TIMEOUT_SECONDS,
    )
    rtnval = CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    return rtnval


def dialect_of(*, database_url: Any) -> str:
    """
        Return the backend name of a SQLAlchemy URL (``sqlite``,
        ``postgresql``, ...).

        :param database_url: URL string or :class:`URL`.

        :returns: Backend name.
    """
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    rtnval = url.get_backend_name()
    return rtnval


def file_sha256(*, path: str) -> str:
    """
        Hex SHA-256 of a file, read in chunks.

        :param path: File path.

        :returns: Hex digest.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if len(chunk) == 0:
                break
            hasher.update(chunk)
    rtnval = hasher.hexdigest()
    return rtnval


# ---------------------------------------------------------------------------
# PostgreSQL connection plumbing
# ---------------------------------------------------------------------------


def _libpq_quote(value: str) -> str:
    """
        Quote a libpq connection-string value.

        :param value: Raw value.

        :returns: ``'value'`` with ``\\`` and ``'`` escaped.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    rtnval = "'{}'".format(escaped)
    return rtnval


def postgres_connection_arguments(*, database_url: Any) -> Tuple[str, Dict[str, str]]:
    """
        Translate a SQLAlchemy PostgreSQL URL into a libpq connection
        string (for ``--dbname``) plus the environment that carries
        the password.

        :param database_url: URL string or :class:`URL`.

        :returns: ``(conninfo, extra_env)``. The password is only in
                  ``extra_env["PGPASSWORD"]``.
    """
    url: URL = make_url(database_url) if isinstance(database_url, str) else database_url
    params: List[Tuple[str, str]] = []
    if url.host:
        params.append(("host", str(url.host)))
    if url.port:
        params.append(("port", str(url.port)))
    if url.username:
        params.append(("user", str(url.username)))
    if url.database:
        params.append(("dbname", str(url.database)))
    for key, value in sorted(dict(url.query).items()):
        if isinstance(value, (list, tuple)):
            value = value[-1]
        params.append((str(key), str(value)))

    conninfo = " ".join("{}={}".format(key, _libpq_quote(value)) for key, value in params)
    extra_env: Dict[str, str] = {}
    if url.password is not None and len(str(url.password)) > 0:
        extra_env["PGPASSWORD"] = str(url.password)
    rtnval = (conninfo, extra_env)
    return rtnval


def _pg_tool(*, name: str, env_override: str) -> str:
    """
        Locate a PostgreSQL client tool.

        :param name: ``pg_dump`` or ``pg_restore``.
        :param env_override: Environment variable that may name the
                             executable explicitly.

        :returns: Executable path.
        :raises: BackupDatabaseError when the tool is not installed.
    """
    configured = os.environ.get(env_override, "")
    if len(configured) > 0:
        return configured
    found = shutil.which(name)
    if found is None:
        err_lines = ["PostgreSQL client tool not found."]
        err_lines.append("TOOL: {}".format(name))
        err_lines.append(
            "HINT: install the postgresql-client package matching the"
            " server version, or set {} to its path.".format(env_override)
        )
        raise BackupDatabaseError(os.linesep.join(err_lines)) from None
    rtnval = found
    return rtnval


def _raise_tool_failure(*, argv: List[str], result: CommandResult) -> None:
    """
        Raise a :class:`BackupDatabaseError` for a failed tool run,
        quoting the tail of its stderr.

        :param argv: Command line that ran.
        :param result: Its outcome.

        :raises: BackupDatabaseError always.
    """
    err_lines = ["{} failed.".format(os.path.basename(argv[0]))]
    err_lines.append("EXIT: {}".format(result.returncode))
    err_lines.append("STDERR: {}".format(result.stderr.strip()[-2000:]))
    raise BackupDatabaseError(os.linesep.join(err_lines)) from None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _sqlite_inventory(*, sqlite_path: str) -> Tuple[int, Optional[str], Dict[str, int]]:
    """
        Count tables and rows in a SQLite file and read its alembic
        revision.

        :param sqlite_path: Database file.

        :returns: ``(table_count, alembic_revision, row_counts)``.
    """
    connection = sqlite3.connect("file:{}?mode=ro".format(sqlite_path), uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        row_counts: Dict[str, int] = {}
        for name in names:
            quoted = '"{}"'.format(name.replace('"', '""'))
            row_counts[name] = int(connection.execute("SELECT COUNT(*) FROM " + quoted).fetchone()[0])
        revision: Optional[str] = None
        if "alembic_version" in names:
            found = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            if found is not None:
                revision = str(found[0])
    finally:
        connection.close()
    rtnval = (len(names), revision, row_counts)
    return rtnval


def _snapshot_sqlite(*, engine: Any, destination_dir: str) -> DatabaseSnapshot:
    """
        Snapshot a SQLite database with the online backup API.

        :param engine: SQLAlchemy engine bound to the database.
        :param destination_dir: Directory to write the snapshot into.

        :returns: :class:`DatabaseSnapshot`.
    """
    file_name = SNAPSHOT_FILE_NAMES[DIALECT_SQLITE]
    destination = os.path.join(destination_dir, file_name)
    raw_connection = engine.raw_connection()
    try:
        source = raw_connection.driver_connection
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        raw_connection.close()
    os.chmod(destination, 0o600)

    table_count, revision, row_counts = _sqlite_inventory(sqlite_path=destination)
    rtnval = DatabaseSnapshot(
        dialect=DIALECT_SQLITE,
        file_path=destination,
        file_name=file_name,
        size_bytes=os.path.getsize(destination),
        sha256=file_sha256(path=destination),
        table_count=table_count,
        alembic_revision=revision,
        row_counts=row_counts,
    )
    return rtnval


def _postgres_inventory(*, engine: Any) -> Tuple[int, Optional[str]]:
    """
        Count tables and read the alembic revision of a PostgreSQL
        database before it is dumped (recorded in the manifest).

        :param engine: SQLAlchemy engine.

        :returns: ``(table_count, alembic_revision)``.
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text as sa_text

    names = sa_inspect(engine).get_table_names()
    revision: Optional[str] = None
    if "alembic_version" in names:
        with engine.connect() as connection:
            found = connection.execute(sa_text("SELECT version_num FROM alembic_version")).fetchone()
            if found is not None:
                revision = str(found[0])
    rtnval = (len(names), revision)
    return rtnval


def dump_postgres(
        *,
        database_url: Any,
        destination: str,
        command_runner: Optional[CommandRunner] = None
    ) -> None:
    """
        ``pg_dump --format=custom`` a database into ``destination``.

        :param database_url: SQLAlchemy URL of the database.
        :param destination: Output file.
        :param command_runner: Tool runner seam.

        :returns: None.
        :raises: BackupDatabaseError on a missing tool or failed run.
    """
    runner = command_runner if command_runner is not None else default_command_runner
    conninfo, extra_env = postgres_connection_arguments(database_url=database_url)
    argv = [
        _pg_tool(name="pg_dump", env_override=ENV_PG_DUMP_PATH),
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file", destination,
        "--dbname", conninfo,
    ]
    result = runner(argv, extra_env)
    if result.returncode != 0:
        _raise_tool_failure(argv=argv, result=result)
    return


def _snapshot_postgres(
        *,
        engine: Any,
        destination_dir: str,
        command_runner: Optional[CommandRunner]
    ) -> DatabaseSnapshot:
    """
        Snapshot a PostgreSQL database with ``pg_dump``.

        :param engine: SQLAlchemy engine bound to the database.
        :param destination_dir: Directory to write the dump into.
        :param command_runner: Tool runner seam.

        :returns: :class:`DatabaseSnapshot`.
    """
    file_name = SNAPSHOT_FILE_NAMES[DIALECT_POSTGRESQL]
    destination = os.path.join(destination_dir, file_name)
    table_count, revision = _postgres_inventory(engine=engine)
    dump_postgres(
        database_url=engine.url,
        destination=destination,
        command_runner=command_runner,
    )
    os.chmod(destination, 0o600)
    rtnval = DatabaseSnapshot(
        dialect=DIALECT_POSTGRESQL,
        file_path=destination,
        file_name=file_name,
        size_bytes=os.path.getsize(destination),
        sha256=file_sha256(path=destination),
        table_count=table_count,
        alembic_revision=revision,
    )
    return rtnval


def snapshot_database(
        *,
        engine: Any,
        destination_dir: str,
        command_runner: Optional[CommandRunner] = None
    ) -> DatabaseSnapshot:
    """
        Write a consistent snapshot of the engine's database into
        ``destination_dir``.

        :param engine: SQLAlchemy engine bound to the database.
        :param destination_dir: Existing directory for the snapshot.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: :class:`DatabaseSnapshot`.
        :raises: BackupDatabaseError for an unsupported dialect or a
                 failed dump.
    """
    dialect = dialect_of(database_url=engine.url)
    if dialect == DIALECT_SQLITE:
        # Works for in-memory databases too: the backup API reads
        # through the engine's own pooled connection.
        rtnval = _snapshot_sqlite(engine=engine, destination_dir=destination_dir)
        return rtnval
    if dialect == DIALECT_POSTGRESQL:
        rtnval = _snapshot_postgres(
            engine=engine,
            destination_dir=destination_dir,
            command_runner=command_runner,
        )
        return rtnval

    err_lines = ["Unsupported database for backup."]
    err_lines.append("DIALECT: {}".format(dialect))
    err_lines.append("SUPPORTED: {}, {}".format(DIALECT_SQLITE, DIALECT_POSTGRESQL))
    raise BackupDatabaseError(os.linesep.join(err_lines)) from None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_database_snapshot(
        *,
        snapshot_path: str,
        dialect: str,
        expected_row_counts: Optional[Dict[str, int]] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> List[SnapshotCheck]:
    """
        Check that a snapshot file can be restored: SQLite passes
        ``PRAGMA integrity_check`` and (when the manifest recorded
        them) holds the recorded row counts; a PostgreSQL dump is
        readable by ``pg_restore --list``.

        :param snapshot_path: Snapshot file.
        :param dialect: ``sqlite`` or ``postgresql``.
        :param expected_row_counts: Row counts from the manifest.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: List of :class:`SnapshotCheck`.
    """
    checks: List[SnapshotCheck] = []
    if dialect == DIALECT_SQLITE:
        try:
            connection = sqlite3.connect("file:{}?mode=ro".format(snapshot_path), uri=True)
            try:
                verdict = connection.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                connection.close()
        except sqlite3.DatabaseError as xcpt:
            verdict = "unreadable: {}".format(xcpt)
        checks.append(SnapshotCheck(
            name="database.integrity",
            ok=verdict == "ok",
            detail="PRAGMA integrity_check: {}".format(verdict),
        ))
        if verdict == "ok" and expected_row_counts:
            _, _, row_counts = _sqlite_inventory(sqlite_path=snapshot_path)
            mismatched = sorted(
                name for name, count in expected_row_counts.items()
                if row_counts.get(name, None) != count
            )
            if len(mismatched) == 0:
                detail = "{} tables hold the recorded row counts".format(len(expected_row_counts))
            else:
                detail = "row counts differ for: {}".format(", ".join(mismatched[:20]))
            checks.append(SnapshotCheck(
                name="database.row_counts",
                ok=len(mismatched) == 0,
                detail=detail,
            ))
        rtnval = checks
        return rtnval

    if dialect == DIALECT_POSTGRESQL:
        runner = command_runner if command_runner is not None else default_command_runner
        try:
            tool = _pg_tool(name="pg_restore", env_override=ENV_PG_RESTORE_PATH)
        except BackupDatabaseError as xcpt:
            checks.append(SnapshotCheck(
                name="database.readable",
                ok=False,
                detail=str(xcpt).splitlines()[0] + " (cannot read the dump on this host)",
            ))
            rtnval = checks
            return rtnval
        argv = [tool, "--list", snapshot_path]
        result = runner(argv, {})
        entries = len([line for line in result.stdout.splitlines() if line and not line.startswith(";")])
        checks.append(SnapshotCheck(
            name="database.readable",
            ok=result.returncode == 0,
            detail=(
                "pg_restore --list read {} TOC entries".format(entries)
                if result.returncode == 0
                else "pg_restore --list failed: {}".format(result.stderr.strip()[-500:])
            ),
        ))
        rtnval = checks
        return rtnval

    checks.append(SnapshotCheck(
        name="database.readable",
        ok=False,
        detail="unsupported dialect {}".format(dialect),
    ))
    rtnval = checks
    return rtnval


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def sqlite_path_from_url(*, database_url: Any) -> str:
    """
        Return the absolute file path of a file-backed SQLite URL.

        :param database_url: URL string or :class:`URL`.

        :returns: Absolute path.
        :raises: BackupDatabaseError for an in-memory database.
    """
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    database = url.database
    if database is None or database in ("", ":memory:") or str(database).startswith("file::memory:"):
        raise BackupDatabaseError("An in-memory SQLite database cannot be restored into.") from None
    rtnval = os.path.abspath(os.path.expanduser(str(database)))
    return rtnval


def _restore_sqlite(
        *,
        database_url: Any,
        snapshot_path: str,
        now: datetime
    ) -> DatabaseRestoreResult:
    """
        Swap a SQLite snapshot into place.

        :param database_url: URL of the database to replace.
        :param snapshot_path: Verified snapshot file.
        :param now: Timestamp used to name the safety copy.

        :returns: :class:`DatabaseRestoreResult`.
    """
    target = sqlite_path_from_url(database_url=database_url)
    target_dir = os.path.dirname(target)
    os.makedirs(target_dir, mode=0o700, exist_ok=True)

    existing = [target] + [target + suffix for suffix in SQLITE_SIDECAR_SUFFIXES]
    existing = [path for path in existing if os.path.exists(path)]
    previous_copy: Optional[str] = None
    if len(existing) > 0:
        previous_copy = os.path.join(
            target_dir, "pre-restore-{}".format(now.strftime("%Y%m%dT%H%M%SZ")),
        )
        os.makedirs(previous_copy, mode=0o700, exist_ok=True)
        for path in existing:
            os.replace(path, os.path.join(previous_copy, os.path.basename(path)))

    staging = target + ".restoring"
    shutil.copyfile(snapshot_path, staging)
    os.chmod(staging, 0o600)
    with open(staging, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(staging, target)

    connection = sqlite3.connect(target)
    try:
        verdict = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if verdict != "ok":
        err_lines = ["Restored SQLite database failed its integrity check."]
        err_lines.append("PATH: {}".format(target))
        err_lines.append("RESULT: {}".format(verdict))
        err_lines.append("PREVIOUS: {}".format(previous_copy))
        raise BackupDatabaseError(os.linesep.join(err_lines)) from None

    rtnval = DatabaseRestoreResult(
        dialect=DIALECT_SQLITE,
        target=target,
        previous_copy=previous_copy,
    )
    return rtnval


def _restore_postgres(
        *,
        database_url: Any,
        snapshot_path: str,
        safety_copy_dir: Optional[str],
        now: datetime,
        command_runner: Optional[CommandRunner]
    ) -> DatabaseRestoreResult:
    """
        Restore a ``pg_dump`` custom-format file over a PostgreSQL
        database in one transaction, after dumping the current state
        as a safety copy.

        :param database_url: URL of the database to replace.
        :param snapshot_path: Verified dump file.
        :param safety_copy_dir: Directory for the pre-restore dump;
                                ``None`` skips it.
        :param now: Timestamp used to name the safety copy.
        :param command_runner: Tool runner seam.

        :returns: :class:`DatabaseRestoreResult`.
    """
    runner = command_runner if command_runner is not None else default_command_runner
    url = make_url(database_url) if isinstance(database_url, str) else database_url

    previous_copy: Optional[str] = None
    if safety_copy_dir is not None:
        os.makedirs(safety_copy_dir, mode=0o700, exist_ok=True)
        previous_copy = os.path.join(
            safety_copy_dir,
            "pre-restore-{}.pgdump".format(now.strftime("%Y%m%dT%H%M%SZ")),
        )
        dump_postgres(database_url=url, destination=previous_copy, command_runner=runner)

    conninfo, extra_env = postgres_connection_arguments(database_url=url)
    argv = [
        _pg_tool(name="pg_restore", env_override=ENV_PG_RESTORE_PATH),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--single-transaction",
        "--exit-on-error",
        "--dbname", conninfo,
        snapshot_path,
    ]
    result = runner(argv, extra_env)
    if result.returncode != 0:
        _raise_tool_failure(argv=argv, result=result)

    rtnval = DatabaseRestoreResult(
        dialect=DIALECT_POSTGRESQL,
        target=str(url.database),
        previous_copy=previous_copy,
    )
    return rtnval


def restore_database(
        *,
        database_url: Any,
        snapshot_path: str,
        dialect: str,
        safety_copy_dir: Optional[str] = None,
        now: Optional[datetime] = None,
        command_runner: Optional[CommandRunner] = None
    ) -> DatabaseRestoreResult:
    """
        Replace the configured database with a snapshot. The service
        must be stopped.

        :param database_url: SQLAlchemy URL of the database to replace.
        :param snapshot_path: Snapshot file taken from the archive.
        :param dialect: Dialect recorded in the archive manifest.
        :param safety_copy_dir: Where PostgreSQL's pre-restore dump
                                goes (SQLite keeps the previous file
                                next to the database).
        :param now: Timestamp for safety-copy names.
        :param command_runner: Tool runner seam (PostgreSQL).

        :returns: :class:`DatabaseRestoreResult`.
        :raises: BackupDatabaseError when the snapshot's dialect does
                 not match the target or the restore fails.
    """
    stamp = now if now is not None else utc_now()
    target_dialect = dialect_of(database_url=database_url)
    if target_dialect != dialect:
        err_lines = ["Backup and target database dialects differ."]
        err_lines.append("BACKUP: {}".format(dialect))
        err_lines.append("TARGET: {}".format(target_dialect))
        raise BackupDatabaseError(os.linesep.join(err_lines)) from None

    if dialect == DIALECT_SQLITE:
        rtnval = _restore_sqlite(database_url=database_url, snapshot_path=snapshot_path, now=stamp)
        return rtnval
    if dialect == DIALECT_POSTGRESQL:
        rtnval = _restore_postgres(
            database_url=database_url,
            snapshot_path=snapshot_path,
            safety_copy_dir=safety_copy_dir,
            now=stamp,
            command_runner=command_runner,
        )
        return rtnval

    raise BackupDatabaseError("Unsupported database dialect: {}".format(dialect)) from None


__all__ = [
    "CommandResult",
    "CommandRunner",
    "DIALECT_POSTGRESQL",
    "DIALECT_SQLITE",
    "DatabaseRestoreResult",
    "DatabaseSnapshot",
    "ENV_PG_DUMP_PATH",
    "ENV_PG_RESTORE_PATH",
    "SNAPSHOT_FILE_NAMES",
    "SnapshotCheck",
    "default_command_runner",
    "dialect_of",
    "dump_postgres",
    "file_sha256",
    "postgres_connection_arguments",
    "restore_database",
    "snapshot_database",
    "sqlite_path_from_url",
    "verify_database_snapshot",
]
