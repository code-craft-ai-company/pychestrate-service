"""
.. module:: tagging.extensions.taxonomy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TagTaxonomyExtension — ResourceExtension base for taxonomies.

.. moduleauthor:: Code Craft AI LLC

A concrete :class:`TagTaxonomyExtension` subclass contributes one
taxonomy to the tag registry. Subclasses set the class variables
``taxonomy_name``, ``case_sensitive_value``, ``allowed_values``,
``color_hex``, and ``description`` and may override
:meth:`validate_value` to add semantic checks beyond membership in
``allowed_values``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, FrozenSet, Optional

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class TagTaxonomyExtension(ResourceExtension):
    """
        Base class declaring a single tag taxonomy.
    """

    resource_extension_name: ClassVar[str] = "tag_taxonomy"
    taxonomy_name: ClassVar[str] = ""
    case_sensitive_value: ClassVar[bool] = False
    allowed_values: ClassVar[Optional[FrozenSet[str]]] = None
    color_hex: ClassVar[str] = "#888888"
    description: ClassVar[str] = ""

    @classmethod
    def validate_value(cls, *, canonical_value: str) -> None:
        """
            Hook called after canonicalization for additional semantic checks.
            The default implementation is a no-op; subclasses raise
            :class:`TagValueValidationError` on failure.

            :param canonical_value: The value after canonicalization.

            :returns: None.
        """
        return
