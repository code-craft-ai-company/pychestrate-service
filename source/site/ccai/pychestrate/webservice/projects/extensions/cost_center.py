"""
.. module:: projects.extensions.cost_center
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference CostCenterFieldExtension.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar

from ccai.pychestrate.webservice.projects.extensions.metadata_field import (
    ProjectMetadataFieldExtension,
)


class CostCenterFieldExtension(ProjectMetadataFieldExtension):
    """
        Reference in-tree metadata field: optional ``cost_center`` string.
    """

    resource_extension_name: ClassVar[str] = "project_metadata_field"
    field_name: ClassVar[str] = "cost_center"
    field_type: ClassVar[str] = "string"
    required: ClassVar[bool] = False
    default_value = None
    description: ClassVar[str] = "Finance cost-center code."
    source_extension: ClassVar[str] = "pychestrate-builtin"
