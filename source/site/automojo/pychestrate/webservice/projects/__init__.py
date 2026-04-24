"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-projects feature — Project aggregate root and member bindings.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
from automojo.pychestrate.webservice.projects.extensions.cost_center import (
    CostCenterFieldExtension,
)
from automojo.pychestrate.webservice.projects.extensions.metadata_field import (
    ProjectMetadataFieldExtension,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree :class:`ProjectMetadataFieldExtension` packs
        for M2: ``cost_center``.

        :returns: None.
    """
    register_resource_extension(
        base_class=ProjectMetadataFieldExtension,
        extension=CostCenterFieldExtension,
    )
    return
