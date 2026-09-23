"""
.. module:: backup
    :synopsis: 10-backup-dr -- backup / disaster-recovery domain.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`BackupRecord`, :class:`BackupStatus` -- persistence row +
  enum.
* :class:`BackupAspects`, :class:`BackupRecordView`,
  :func:`trigger_backup`, :func:`get_backup`, :func:`list_backups`,
  :func:`verify_backup`, :func:`plan_restore`,
  :func:`restore_backup`, :func:`prune_backups` -- the orchestrator
  facade (see :mod:`backup.service`).
* :class:`BackupStorageBackendProtocol` factory contract +
  reference :class:`LocalFilesystemBackupBackend`.
* :class:`BackupEventTopics`.
* Errors: :class:`BackupError` and its subclasses.
* :func:`register_builtin_extensions`.

The operator command is ``python -m ccai.pychestrate.admin backup``
(:mod:`backup.cli`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.backup.errors import (
    BackupArchiveInvalidError,
    BackupBackendUnavailableError,
    BackupDatabaseError,
    BackupError,
    BackupKeyMaterialError,
    BackupRecordNotFoundError,
    BackupRequestInvalidError,
    BackupRestoreRequiresOfflineError,
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
    plan_restore,
    prune_backups,
    restore_backup,
    trigger_backup,
    verify_backup,
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
    "BackupArchiveInvalidError",
    "BackupBackendUnavailableError",
    "BackupDatabaseError",
    "BackupKeyMaterialError",
    "BackupRecordNotFoundError",
    "BackupRequestInvalidError",
    "BackupRestoreRequiresOfflineError",
    "BackupStorageBackendProtocol",
    "LocalFilesystemBackupBackend",
    "trigger_backup",
    "get_backup",
    "list_backups",
    "plan_restore",
    "prune_backups",
    "restore_backup",
    "verify_backup",
    "register_builtin_extensions",
]
