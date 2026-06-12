"""
.. module:: tagging.extensions.environment
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference EnvironmentTaxonomy.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, FrozenSet, Optional

from ccai.pychestrate.webservice.tagging.extensions.taxonomy import TagTaxonomyExtension


class EnvironmentTaxonomy(TagTaxonomyExtension):
    """
        Standard ``env`` taxonomy with the canonical deployment tiers.
    """
    resource_extension_name: ClassVar[str] = "tag_taxonomy"
    taxonomy_name: ClassVar[str] = "env"
    case_sensitive_value: ClassVar[bool] = False
    allowed_values: ClassVar[Optional[FrozenSet[str]]] = frozenset({
        "dev", "test", "stage", "prod", "sandbox",
    })
    color_hex: ClassVar[str] = "#4285f4"
    description: ClassVar[str] = "Deployment environment tier."


class PlatformTaxonomy(TagTaxonomyExtension):
    """
        Standard ``platform`` taxonomy.
    """
    resource_extension_name: ClassVar[str] = "tag_taxonomy"
    taxonomy_name: ClassVar[str] = "platform"
    case_sensitive_value: ClassVar[bool] = False
    allowed_values: ClassVar[Optional[FrozenSet[str]]] = frozenset({
        "linux", "macos", "windows", "freebsd", "other",
    })
    color_hex: ClassVar[str] = "#34a853"
    description: ClassVar[str] = "Target operating-system platform."


class ComplianceTaxonomy(TagTaxonomyExtension):
    """
        Standard ``compliance`` taxonomy.
    """
    resource_extension_name: ClassVar[str] = "tag_taxonomy"
    taxonomy_name: ClassVar[str] = "compliance"
    case_sensitive_value: ClassVar[bool] = False
    allowed_values: ClassVar[Optional[FrozenSet[str]]] = frozenset({
        "public", "internal", "confidential", "restricted", "pci", "hipaa", "fedramp",
    })
    color_hex: ClassVar[str] = "#ea4335"
    description: ClassVar[str] = "Data-handling / compliance class."
