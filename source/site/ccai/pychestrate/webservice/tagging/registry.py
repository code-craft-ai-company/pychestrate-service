"""
.. module:: tagging.registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Runtime index over registered TagTaxonomyExtension subclasses.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Dict, Tuple, Type

from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from ccai.pychestrate.webservice.tagging.exceptions import TaxonomyNotFoundError
from ccai.pychestrate.webservice.tagging.extensions.taxonomy import TagTaxonomyExtension


def load_registered_taxonomies() -> Dict[str, Type[TagTaxonomyExtension]]:
    """
        Return a ``taxonomy_name → class`` mapping over every registered
        :class:`TagTaxonomyExtension`.

        :returns: Dict keyed by taxonomy name.
        :raises: ConfigurationError on duplicate or empty names.
    """
    packs: Tuple[Type[TagTaxonomyExtension], ...] = list_resource_extensions(
        base_class=TagTaxonomyExtension
    )
    rtnval = check_unique_identifiers(
        packs=packs,
        identifier_attribute="taxonomy_name",
        category_label="TagTaxonomyExtension",
    )
    return rtnval


def get_taxonomy(*, taxonomy_name: str) -> Type[TagTaxonomyExtension]:
    """
        Look up a registered taxonomy class by name.

        :param taxonomy_name: Canonical taxonomy name.

        :returns: The matching class.
        :raises: TaxonomyNotFoundError
    """
    registry = load_registered_taxonomies()
    pack = registry.get(taxonomy_name, None)
    if pack is None:
        err_msg_lines = ["Requested taxonomy is not registered."]
        err_msg_lines.append("TAXONOMY: {}".format(taxonomy_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise TaxonomyNotFoundError(err_msg)

    rtnval = pack
    return rtnval
