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
        Backup / disaster-recovery bus topics. The p21d milestone
        emits STARTED + COMPLETED + FAILED for a manually-triggered
        backup; scheduled / drill / restore-verified topics land
        with the scheduler follow-on.
    """
    STARTED = "entity.backup.started"
    COMPLETED = "entity.backup.completed"
    FAILED = "entity.backup.failed"
    RESTORE_REQUESTED = "entity.backup.restore_requested"
