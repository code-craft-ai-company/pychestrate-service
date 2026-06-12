"""
.. module:: tagging
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-tagging feature — canonical tag assignments with taxonomy registry.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import register_resource_extension
from ccai.pychestrate.webservice.tagging.extensions.environment import (
    ComplianceTaxonomy,
    EnvironmentTaxonomy,
    PlatformTaxonomy,
)
from ccai.pychestrate.webservice.tagging.extensions.taxonomy import TagTaxonomyExtension


def register_builtin_extensions() -> None:
    """
        Register the in-tree M2 taxonomy packs (``env``, ``platform``,
        ``compliance``).

        :returns: None.
    """
    register_resource_extension(
        base_class=TagTaxonomyExtension, extension=EnvironmentTaxonomy,
    )
    register_resource_extension(
        base_class=TagTaxonomyExtension, extension=PlatformTaxonomy,
    )
    register_resource_extension(
        base_class=TagTaxonomyExtension, extension=ComplianceTaxonomy,
    )
    return
