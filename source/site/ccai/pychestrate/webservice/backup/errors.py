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


class BackupRestoreNotImplementedError(BackupError):
    """
        Raised when a restore is requested but the restore
        executor has not yet shipped. Restore is a documented
        follow-up for the p21d milestone.
    """
