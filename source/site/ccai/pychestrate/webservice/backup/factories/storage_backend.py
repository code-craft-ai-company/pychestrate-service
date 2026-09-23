"""
.. module:: backup.factories.storage_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for the pluggable backup_storage_backend.

.. moduleauthor:: Code Craft AI LLC

A ``backup_storage_backend`` implementation owns the destination
that backup archives are written to. The p21d milestone ships the
in-tree :class:`LocalFilesystemBackupBackend` reference for
dev / test; production wiring (S3, Azure Blob, GCS, SMB / NFS
mirror) is a follow-on that inherits this same protocol.

The protocol is deliberately narrow: the backup service hands the
backend a finished archive (a file, or for the original byte API a
byte-string) plus the backup id, and the backend returns an opaque
``archive_uri`` describing where it landed. Backends are stateless
aside from the destination they were configured with.

:meth:`store_archive_file` and :meth:`local_archive_path` default to
the byte API / "not local" so a backend that only implements
:meth:`write_archive` keeps working.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import List, Optional

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class BackupArchiveWriteResult:
    """
        Result returned by a backup-archive write.

        :param archive_uri: Opaque, backend-resolved location of the
                             written archive.
        :param size_bytes: Number of bytes written.
    """
    archive_uri: str
    size_bytes: int


class BackupStorageBackendProtocol(FactoryProtocolBase):
    """
        Contract for a ``backup_storage_backend`` implementation --
        the pluggable destination for backup archives.
    """

    factory_protocol_name: str = "backup_storage_backend"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = (
        "https://docs.pychestrate.io/plugin-api/backup_storage_backend"
    )
    published_reference: str = (
        "ccai.pychestrate.webservice.backup.factories.local_backend"
        ".LocalFilesystemBackupBackend"
    )

    @classmethod
    def backend_kind(cls) -> str:
        """
            Return the short kind identifier recorded on the
            backup record (e.g. ``local_filesystem``).

            :returns: The backend-kind string.
        """
        raise NotImplementedError(
            "Subclasses must implement backend_kind"
        )

    @classmethod
    def write_archive(
            cls,
            *,
            backup_id: str,
            archive_bytes: bytes
        ) -> BackupArchiveWriteResult:
        """
            Persist a finished backup archive.

            :param backup_id: The backup record UUID.
            :param archive_bytes: The complete archive byte-string.

            :returns: The :class:`BackupArchiveWriteResult`.
            :raises: BackupBackendUnavailableError
        """
        raise NotImplementedError(
            "Subclasses must implement write_archive"
        )

    @classmethod
    def list_archives(cls) -> List[str]:
        """
            Return the archive URIs the backend currently holds.

            :returns: A list of opaque archive-URI strings.
        """
        raise NotImplementedError(
            "Subclasses must implement list_archives"
        )

    @classmethod
    def store_archive_file(
            cls,
            *,
            backup_id: str,
            source_path: str
        ) -> BackupArchiveWriteResult:
        """
            Persist a finished archive file. The default reads the file
            and delegates to :meth:`write_archive`; backends that can
            move or stream a file override it.

            :param backup_id: The backup record UUID.
            :param source_path: Local archive file (the backend may
                                consume it).

            :returns: The :class:`BackupArchiveWriteResult`.
            :raises: BackupBackendUnavailableError
        """
        with open(source_path, "rb") as handle:
            archive_bytes = handle.read()
        rtnval = cls.write_archive(backup_id=backup_id, archive_bytes=archive_bytes)
        return rtnval

    @classmethod
    def local_archive_path(cls, *, archive_uri: str) -> Optional[str]:
        """
            Map an archive URI to a readable local file, for
            verification and restore. Remote backends return ``None``
            (the operator fetches the archive and restores from the
            file).

            :param archive_uri: URI returned by a write.

            :returns: Local path or ``None``.
        """
        rtnval = None
        return rtnval
