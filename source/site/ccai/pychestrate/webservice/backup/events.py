"""
.. module:: backup.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Backup / disaster-recovery bus topic constants.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class BackupEventTopics:
    """
        Backup / disaster-recovery topics, used as the ``topic=``
        field of the backup log events.
    """
    STARTED = "entity.backup.started"
    COMPLETED = "entity.backup.completed"
    FAILED = "entity.backup.failed"
    RESTORE_REQUESTED = "entity.backup.restore_requested"
    RESTORE_VERIFIED = "entity.backup.restore_verified"
    RESTORE_COMPLETED = "entity.backup.restore_completed"
