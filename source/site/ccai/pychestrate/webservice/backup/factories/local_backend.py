"""
.. module:: backup.factories.local_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference local-filesystem backup_storage_backend.

.. moduleauthor:: Code Craft AI LLC

:class:`LocalFilesystemBackupBackend` writes backup archives under
a configurable root directory (defaults to a ``backups`` directory
inside the service workspace). It mirrors how
``secrets.factories.local_backend`` and ``jobs/results`` do local
storage for dev / test: the only I/O is the archive file itself,
which keeps the backend trivial to exercise from tests.

The archive is written atomically -- bytes land in a ``.partial``
sibling and are renamed into place -- so a crash mid-write never
leaves a half-written archive that a later read could mistake for
a good backup.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List

from ccai.pychestrate.webservice.backup.errors import (
    BackupBackendUnavailableError,
)
from ccai.pychestrate.webservice.backup.factories.storage_backend import (
    BackupArchiveWriteResult,
    BackupStorageBackendProtocol,
)


DEFAULT_BACKUP_ROOT_ENV_VAR: str = "PYCHESTRATE_BACKUP_ROOT"
DEFAULT_BACKUP_ROOT: str = "/tmp/pychestrate-backups"

ARCHIVE_SUFFIX: str = ".backup.tar"


def _resolve_backup_root() -> str:
    """
        Resolve the local backup-root directory from the
        environment, falling back to a stable default.

        :returns: An absolute directory path.
    """
    configured = os.environ.get(DEFAULT_BACKUP_ROOT_ENV_VAR, None)
    if configured is not None and len(configured) > 0:
        rtnval = configured
        return rtnval
    rtnval = DEFAULT_BACKUP_ROOT
    return rtnval


class LocalFilesystemBackupBackend(BackupStorageBackendProtocol):
    """
        Reference ``backup_storage_backend`` that writes archives
        to the local filesystem. Intended for dev / test wiring.
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
            Persist a finished archive under the local backup root.

            :param backup_id: The backup record UUID.
            :param archive_bytes: The complete archive byte-string.

            :returns: The :class:`BackupArchiveWriteResult`.
            :raises: BackupBackendUnavailableError
        """
        root = _resolve_backup_root()
        try:
            os.makedirs(root, exist_ok=True)
        except OSError as xcpt:
            err_msg_lines = [
                "Failed to create the local backup root directory.",
            ]
            err_msg_lines.append("ROOT: {}".format(root))
            err_msg_lines.append("CAUSE: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_msg_lines)
            raise BackupBackendUnavailableError(err_msg) from None

        final_name = backup_id + ARCHIVE_SUFFIX
        final_path = os.path.join(root, final_name)
        partial_path = final_path + ".partial"

        try:
            with open(partial_path, "wb") as archive_file:
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
        archive_uri = "file://" + final_path
        rtnval = BackupArchiveWriteResult(
            archive_uri=archive_uri,
            size_bytes=size_bytes,
        )
        return rtnval

    @classmethod
    def list_archives(cls) -> List[str]:
        """
            Return the archive URIs currently held under the
            local backup root.

            :returns: A list of ``file://`` archive URIs.
        """
        root = _resolve_backup_root()
        rtnval: List[str] = []
        if os.path.isdir(root) is False:
            return rtnval

        for entry in sorted(os.listdir(root)):
            if entry.endswith(ARCHIVE_SUFFIX) is False:
                continue
            entry_path = os.path.join(root, entry)
            rtnval.append("file://" + entry_path)
        return rtnval
