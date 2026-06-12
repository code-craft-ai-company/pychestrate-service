"""
.. module:: project_templates
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-project-templates feature — ProjectTemplateExtension registry.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_resource_extension
from ccai.pychestrate.webservice.project_templates.extensions.standard_ci import (
    ComplianceProjectTemplate,
    StandardCiTemplate,
)
from ccai.pychestrate.webservice.project_templates.extensions.template import (
    ProjectTemplateExtension,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree M2 :class:`ProjectTemplateExtension` packs.

        :returns: None.
    """
    register_resource_extension(
        base_class=ProjectTemplateExtension, extension=StandardCiTemplate,
    )
    register_resource_extension(
        base_class=ProjectTemplateExtension, extension=ComplianceProjectTemplate,
    )
    return
