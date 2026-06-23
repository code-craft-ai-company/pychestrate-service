"""
.. module:: backup
    :synopsis: 10-backup-dr -- backup / disaster-recovery domain.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`BackupRecord`, :class:`BackupStatus` -- persistence row +
  enum.
* :class:`BackupAspects`, :class:`BackupRecordView`,
  :func:`trigger_backup`, :func:`get_backup`, :func:`list_backups`,
  :func:`request_restore` -- the orchestrator facade.
* :class:`BackupStorageBackendProtocol` factory contract +
  reference :class:`LocalFilesystemBackupBackend`.
* :class:`BackupEventTopics`.
* Errors: :class:`BackupError`, :class:`BackupRecordNotFoundError`,
  :class:`BackupBackendUnavailableError`,
  :class:`BackupRequestInvalidError`,
  :class:`BackupRestoreNotImplementedError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.backup.errors import (
    BackupBackendUnavailableError,
    BackupError,
    BackupRecordNotFoundError,
    BackupRequestInvalidError,
    BackupRestoreNotImplementedError,
)
from ccai.pychestrate.webservice.backup.events import (
    BackupEventTopics,
)
from ccai.pychestrate.webservice.backup.factories.local_backend import (
    LocalFilesystemBackupBackend,
)
from ccai.pychestrate.webservice.backup.factories.storage_backend import (
    BackupStorageBackendProtocol,
)
from ccai.pychestrate.webservice.backup.models import (
    BackupRecord,
    BackupStatus,
)
from ccai.pychestrate.webservice.backup.service import (
    BackupAspects,
    BackupRecordView,
    get_backup,
    list_backups,
    request_restore,
    trigger_backup,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`LocalFilesystemBackupBackend`
        reference ``backup_storage_backend`` implementation.

        :returns: None.
    """
    register_factory_implementation(
        implementation=LocalFilesystemBackupBackend,
    )
    return


__all__ = [
    "BackupRecord",
    "BackupStatus",
    "BackupAspects",
    "BackupRecordView",
    "BackupEventTopics",
    "BackupError",
    "BackupRecordNotFoundError",
    "BackupBackendUnavailableError",
    "BackupRequestInvalidError",
    "BackupRestoreNotImplementedError",
    "BackupStorageBackendProtocol",
    "LocalFilesystemBackupBackend",
    "trigger_backup",
    "get_backup",
    "list_backups",
    "request_restore",
    "register_builtin_extensions",
]
