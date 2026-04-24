"""
.. module:: retention
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-retention-policies feature — policy records + action chain.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_factory_implementation
from automojo.pychestrate.webservice.retention.factories.additional_actions import (
    ArchiveAction,
    PermanentArchiveAction,
    TierMoveAction,
)
from automojo.pychestrate.webservice.retention.factories.delete_action import DeleteAction


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``retention_action`` implementations: delete,
        tier_move, archive, permanent_archive.

        :returns: None.
    """
    register_factory_implementation(implementation=DeleteAction)
    register_factory_implementation(implementation=TierMoveAction)
    register_factory_implementation(implementation=ArchiveAction)
    register_factory_implementation(implementation=PermanentArchiveAction)
    return
