"""
.. module:: tagging
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-tagging feature — canonical tag assignments with taxonomy registry.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
from automojo.pychestrate.webservice.tagging.extensions.environment import (
    ComplianceTaxonomy,
    EnvironmentTaxonomy,
    PlatformTaxonomy,
)
from automojo.pychestrate.webservice.tagging.extensions.taxonomy import TagTaxonomyExtension


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
