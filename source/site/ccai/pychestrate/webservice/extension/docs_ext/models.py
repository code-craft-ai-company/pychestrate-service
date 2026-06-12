"""
.. module:: extension.docs_ext.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build-time dataclasses for emitted Sphinx pages.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional


PAGE_KIND_PROTOCOL: str = "protocol"
PAGE_KIND_RESOURCE: str = "resource"


@dataclass(frozen=True)
class DocPage:
    """
        Single page rendered into the ``docs/extensions`` tree.

        :param name: Catalog entry name (protocol name or resource
                     class name).
        :param kind: ``"protocol"`` for factory protocols,
                     ``"resource"`` for resource bases.
        :param status: Catalog ``status`` value.
        :param schema_version: ``protocol_schema_version`` reported by
                               the entry.
        :param min_schema_version: Earliest schema honored by the host.
        :param deprecation_date: ISO-8601 date string or None.
        :param sunset_date: ISO-8601 date string or None.
        :param docs_url: External documentation URL.
        :param reference: Dotted path to the in-tree reference.
        :param declaring_class: ``module.ClassName`` declaring the entry.
    """
    name: str
    kind: str
    status: str
    schema_version: int
    min_schema_version: int
    deprecation_date: Optional[str]
    sunset_date: Optional[str]
    docs_url: str
    reference: str
    declaring_class: str
