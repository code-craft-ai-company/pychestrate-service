"""
.. module:: backup.factories.local_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference local-filesystem backup_storage_backend.

.. moduleauthor:: Code Craft AI LLC

:class:`LocalFilesystemBackupBackend` keeps backup archives in the
backup root (``PYCHESTRATE_BACKUP_ROOT``, default
``<presence_dir>/backups``; see :mod:`backup.locations`). The
directory is created mode 0700 -- archives carry the whole database.
It is the single-host deployment's backend: an operator copies the
directory (archives + ``.sha256`` sidecars) off the host on a
schedule.

Writes are atomic -- bytes land in a ``.partial`` sibling (or the
finished archive is renamed in from the staging directory) -- so a
crash mid-write never leaves a half-written archive that a later
read could mistake for a good backup.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil

from typing import List, Optional

from ccai.pychestrate.webservice.backup.errors import (
    BackupBackendUnavailableError,
)
from ccai.pychestrate.webservice.backup.factories.storage_backend import (
    BackupArchiveWriteResult,
    BackupStorageBackendProtocol,
)
from ccai.pychestrate.webservice.backup.locations import (
    ENV_BACKUP_ROOT,
    ensure_private_directory,
    resolve_backup_root,
)


DEFAULT_BACKUP_ROOT_ENV_VAR: str = ENV_BACKUP_ROOT

#: Suffix of the archives :meth:`LocalFilesystemBackupBackend.store_archive_file` writes.
ARCHIVE_SUFFIX: str = ".backup.tar.gz"

#: Suffix of archives written through the byte API
#: (:meth:`LocalFilesystemBackupBackend.write_archive`).
LEGACY_ARCHIVE_SUFFIX: str = ".backup.tar"

FILE_URI_PREFIX: str = "file://"


def _prepare_root() -> str:
    """
        Resolve and create (mode 0700) the backup root.

        :returns: Absolute directory path.
        :raises: BackupBackendUnavailableError when it cannot be created.
    """
    root = resolve_backup_root()
    try:
        ensure_private_directory(path=root)
    except OSError as xcpt:
        err_msg_lines = [
            "Failed to create the local backup root directory.",
        ]
        err_msg_lines.append("ROOT: {}".format(root))
        err_msg_lines.append("CAUSE: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_msg_lines)
        raise BackupBackendUnavailableError(err_msg) from None
    rtnval = root
    return rtnval


class LocalFilesystemBackupBackend(BackupStorageBackendProtocol):
    """
        Reference ``backup_storage_backend`` that keeps archives on
        the local filesystem.
    """

    factory_protocol_name: str = "backup_storage_backend"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 500

    @classmethod
    def backend_kind(cls) -> str:
        """
            Return the short kind identifier for this backend.

            :returns: The string ``local_filesystem``.
        """
        rtnval = "local_filesystem"
        return rtnval

    @classmethod
    def write_archive(
            cls,
            *,
            backup_id: str,
            archive_bytes: bytes
        ) -> BackupArchiveWriteResult:
        """
            Persist an in-memory archive under the backup root as
            ``<backup_id>.backup.tar``.

            :param backup_id: The backup record UUID.
            :param archive_bytes: The complete archive byte-string.

            :returns: The :class:`BackupArchiveWriteResult`.
            :raises: BackupBackendUnavailableError
        """
        root = _prepare_root()

        final_name = backup_id + LEGACY_ARCHIVE_SUFFIX
        final_path = os.path.join(root, final_name)
        partial_path = final_path + ".partial"

        try:
            descriptor = os.open(partial_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as archive_file:
                archive_file.write(archive_bytes)
            os.replace(partial_path, final_path)
        except OSError as xcpt:
            err_msg_lines = [
                "Failed to write the backup archive to local storage.",
            ]
            err_msg_lines.append("PATH: {}".format(final_path))
            err_msg_lines.append("CAUSE: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_msg_lines)
            raise BackupBackendUnavailableError(err_msg) from None

        size_bytes = len(archive_bytes)
        archive_uri = FILE_URI_PREFIX + final_path
        rtnval = BackupArchiveWriteResult(
            archive_uri=archive_uri,
            size_bytes=size_bytes,
        )
        return rtnval

    @classmethod
    def store_archive_file(
            cls,
            *,
            backup_id: str,
            source_path: str
        ) -> BackupArchiveWriteResult:
        """
            Move a finished archive file into the backup root as
            ``<backup_id>.backup.tar.gz`` (a rename when the staging
            directory is on the same filesystem, else copy + rename).

            :param backup_id: The backup record UUID.
            :param source_path: Finished archive in the staging area.

            :returns: The :class:`BackupArchiveWriteResult`.
            :raises: BackupBackendUnavailableError
        """
        root = _prepare_root()
        final_path = os.path.join(root, backup_id + ARCHIVE_SUFFIX)
        partial_path = final_path + ".partial"
        try:
            try:
                os.replace(source_path, final_path)
            except OSError:
                shutil.copyfile(source_path, partial_path)
                os.chmod(partial_path, 0o600)
                os.replace(partial_path, final_path)
                os.remove(source_path)
        except OSError as xcpt:
            err_msg_lines = [
                "Failed to store the backup archive in local storage.",
            ]
            err_msg_lines.append("PATH: {}".format(final_path))
            err_msg_lines.append("CAUSE: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_msg_lines)
            raise BackupBackendUnavailableError(err_msg) from None

        rtnval = BackupArchiveWriteResult(
            archive_uri=FILE_URI_PREFIX + final_path,
            size_bytes=os.path.getsize(final_path),
        )
        return rtnval

    @classmethod
    def local_archive_uri(cls, *, path: str) -> str:
        """
            The URI this backend records for a local archive file.

            :param path: Archive path.

            :returns: ``file://`` URI.
        """
        rtnval = FILE_URI_PREFIX + os.path.abspath(path)
        return rtnval

    @classmethod
    def local_archive_path(cls, *, archive_uri: str) -> Optional[str]:
        """
            Map a ``file://`` archive URI back to its path.

            :param archive_uri: URI returned by a write.

            :returns: Local path, or ``None`` for another scheme.
        """
        if archive_uri is None or archive_uri.startswith(FILE_URI_PREFIX) is False:
            return None
        rtnval = archive_uri[len(FILE_URI_PREFIX):]
        return rtnval

    @classmethod
    def list_archives(cls) -> List[str]:
        """
            Return the archive URIs currently held under the
            local backup root.

            :returns: A list of ``file://`` archive URIs.
        """
        root = resolve_backup_root()
        rtnval: List[str] = []
        if os.path.isdir(root) is False:
            return rtnval

        for entry in sorted(os.listdir(root)):
            if entry.endswith(ARCHIVE_SUFFIX) is False and entry.endswith(LEGACY_ARCHIVE_SUFFIX) is False:
                continue
            entry_path = os.path.join(root, entry)
            rtnval.append(FILE_URI_PREFIX + entry_path)
        return rtnval
