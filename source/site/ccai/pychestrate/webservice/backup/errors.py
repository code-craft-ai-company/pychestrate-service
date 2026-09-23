"""
.. module:: backup.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Backup / disaster-recovery exception hierarchy.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class BackupError(Exception):
    """
        Base for recoverable backup / disaster-recovery errors.
    """


class BackupRecordNotFoundError(BackupError):
    """
        Raised when a backup-record lookup misses.
    """


class BackupBackendUnavailableError(BackupError):
    """
        Raised when the configured ``backup_storage_backend``
        cannot accept an archive write.
    """


class BackupRequestInvalidError(BackupError):
    """
        Raised when a caller-supplied backup-trigger request
        violates an invariant (e.g. no substrate selected).
    """


class BackupDatabaseError(BackupError):
    """
        Raised when the database cannot be snapshotted or restored:
        an unsupported dialect, a missing ``pg_dump`` / ``pg_restore``,
        a non-zero tool exit, or a snapshot that fails its integrity
        check.
    """


class BackupKeyMaterialError(BackupError):
    """
        Raised when key material cannot be read at backup time, or a
        key bundle does not match its archive / would overwrite a
        different key at restore time.
    """


class BackupArchiveInvalidError(BackupError):
    """
        Raised when a backup archive or key bundle is unreadable,
        fails its checksum, carries an unsafe member path, or has an
        unrecognized manifest.
    """


class BackupRestoreRequiresOfflineError(BackupError):
    """
        Raised when a restore is requested from the running service.
        A restore replaces the database, the run artifacts and the
        key material the process has loaded, so it runs with the
        service stopped, through the operator command
        ``python -m ccai.pychestrate.admin backup restore``.

        :ivar restore_command: The exact command to run.
    """

    def __init__(self, message: str, *, restore_command: str) -> None:
        super().__init__(message)
        self.restore_command: str = restore_command
        return
