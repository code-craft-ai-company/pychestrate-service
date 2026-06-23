"""
.. module:: hardening.collisions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Extension-collision detection helpers.

.. moduleauthor:: Code Craft AI LLC

Every Layer-2 feature that exposes a ``ResourceExtension`` subclass
registers a unique identifier per pack (``field_name``, ``taxonomy_name``,
``template_id``, ``action_name``, etc.). This module centralizes the
``duplicate identifier → ConfigurationError`` check so feature code can
call it during bootstrap without repeating the pattern.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Dict, Iterable, Type

from ccai.errors.exceptions import ConfigurationError


def check_unique_identifiers(
        *,
        packs: Iterable[Type[object]],
        identifier_attribute: str,
        category_label: str
    ) -> Dict[str, Type[object]]:
    """
        Return a ``identifier → class`` mapping after verifying every
        supplied pack carries a unique, non-empty identifier.

        :param packs: Iterable of classes registered for the category.
        :param identifier_attribute: Name of the class attribute that
                                     holds the identifier (e.g.
                                     ``taxonomy_name``).
        :param category_label: Free-text label used in error messages
                               (e.g. ``TagTaxonomyExtension``).

        :returns: Dict keyed by identifier.
        :raises: ConfigurationError on duplicate or empty identifier.
    """
    rtnval: Dict[str, Type[object]] = {}
    for pack in packs:
        identifier = getattr(pack, identifier_attribute, "")
        if identifier is None or len(str(identifier)) == 0:
            err_msg_lines = ["{} declares an empty {}.".format(category_label, identifier_attribute)]
            err_msg_lines.append("CLASS: {}".format(pack.__qualname__))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)

        if identifier in rtnval:
            err_msg_lines = ["Duplicate {} value across {} subclasses.".format(
                identifier_attribute, category_label,
            )]
            err_msg_lines.append("VALUE: {}".format(identifier))
            err_msg_lines.append("FIRST: {}".format(rtnval[identifier].__qualname__))
            err_msg_lines.append("SECOND: {}".format(pack.__qualname__))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)

        rtnval[identifier] = pack

    return rtnval
