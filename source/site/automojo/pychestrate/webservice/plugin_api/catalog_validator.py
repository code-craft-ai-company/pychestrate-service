"""
.. module:: plugin_api.catalog_validator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Resolve every catalog entry's ``published_reference`` import.

.. moduleauthor:: Automation Mojo LLC

A drift between the ``is_published`` annotation set and the in-tree
reference implementation should crash the service at startup rather
than silently shipping an incomplete catalog. The validator imports
each entry's ``published_reference`` dotted path and confirms the
target attribute exists. M2 extends this check to compare
``protocol_schema_version`` between the entry and the resolved
reference.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib
import os

from typing import List

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.plugin_api.catalog_builder import (
    Catalog,
    CatalogEntry,
)


REASON_REFERENCE_MISSING: str = "published_protocol_reference_missing"
REASON_REFERENCE_NOT_IMPORTABLE: str = "published_protocol_reference_not_importable"
REASON_REFERENCE_ATTR_MISSING: str = "published_protocol_reference_attribute_missing"


def _resolve_dotted_path(*, dotted: str):
    """
        Import the module portion and return the named attribute.

        :param dotted: ``module.path.AttrName`` style reference.

        :returns: The resolved attribute object.
        :raises: ConfigurationError on bad path / missing attribute.
    """
    if dotted is None or len(dotted) == 0:
        err_msg_lines = ["Empty published_reference."]
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    if "." not in dotted:
        err_msg_lines = ["published_reference must be ``module.path.AttrName``."]
        err_msg_lines.append("VALUE: {!r}".format(dotted))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    module_path, _, attr_name = dotted.rpartition(".")
    try:
        module = importlib.import_module(module_path)
    except Exception as xcpt:
        err_msg_lines = ["Could not import module for published_reference."]
        err_msg_lines.append("REFERENCE: {}".format(dotted))
        err_msg_lines.append("MODULE: {}".format(module_path))
        err_msg_lines.append("ERROR: {}".format(xcpt))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    if not hasattr(module, attr_name):
        err_msg_lines = ["published_reference attribute is not present in module."]
        err_msg_lines.append("REFERENCE: {}".format(dotted))
        err_msg_lines.append("MODULE: {}".format(module_path))
        err_msg_lines.append("ATTR: {}".format(attr_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    rtnval = getattr(module, attr_name)
    return rtnval


def _validate_entry(*, entry: CatalogEntry) -> None:
    """
        Resolve a single :class:`CatalogEntry`'s reference.

        :param entry: Catalog entry under validation.

        :returns: None.
        :raises: ConfigurationError on any unresolved reference.
    """
    reference = entry.metadata.reference
    if reference is None or len(reference) == 0:
        err_msg_lines = ["Catalog entry has empty published_reference."]
        err_msg_lines.append("ENTRY_NAME: {}".format(entry.name))
        err_msg_lines.append("ENTRY_KIND: {}".format(entry.kind))
        err_msg_lines.append("REASON: {}".format(REASON_REFERENCE_MISSING))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    _resolve_dotted_path(dotted=reference)
    return


def validate_catalog_against_code(*, catalog: Catalog) -> List[CatalogEntry]:
    """
        Validate every entry's ``published_reference`` resolves.

        :param catalog: :class:`Catalog` snapshot.

        :returns: Same list of entries that were validated (factory +
                  resource) for caller diagnostics.
        :raises: ConfigurationError on the first unresolved entry.
    """
    validated: List[CatalogEntry] = []
    for entry in catalog.factory_entries:
        _validate_entry(entry=entry)
        validated.append(entry)
    for entry in catalog.resource_entries:
        _validate_entry(entry=entry)
        validated.append(entry)
    rtnval = validated
    return rtnval
