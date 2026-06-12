"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-projects feature — Project aggregate root and member bindings.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_resource_extension
from ccai.pychestrate.webservice.projects.extensions.cost_center import (
    CostCenterFieldExtension,
)
from ccai.pychestrate.webservice.projects.extensions.metadata_field import (
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
