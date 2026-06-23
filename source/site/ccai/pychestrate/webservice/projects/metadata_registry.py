"""
.. module:: projects.metadata_registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Runtime registry over :class:`ProjectMetadataFieldExtension` subclasses.

.. moduleauthor:: Code Craft AI LLC

The registry is populated by :mod:`ccai.pychestrate.webservice.extensions.bootstrap`
during ``register_phase1_builtin_extensions``. Once that bootstrap hook
finishes it calls :func:`freeze_registry` which locks the set of packs
so subsequent mutations raise :class:`ConfigurationError`. That matches
the 2-projects spec requirement that the metadata field registry is
final on ``on_service_ready``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from typing import Dict, Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from ccai.pychestrate.webservice.projects.extensions.metadata_field import (
    ProjectMetadataFieldExtension,
)


_REGISTRY_LOCK = threading.RLock()
_FROZEN_FIELDS: Dict[str, Type[ProjectMetadataFieldExtension]] = {}
_IS_FROZEN: bool = False


def freeze_registry() -> Dict[str, Type[ProjectMetadataFieldExtension]]:
    """
        Freeze the current set of :class:`ProjectMetadataFieldExtension`
        packs. After this runs :func:`load_registered_fields` returns
        the frozen map; any attempt to register a new field via
        :func:`register_resource_extension` followed by a subsequent
        :func:`freeze_registry` call is rejected unless
        :func:`reset_for_testing` has run first.

        :returns: The frozen field_name -> class mapping.
        :raises: ConfigurationError when two packs declare the same
                 ``field_name``.
    """
    global _IS_FROZEN
    packs = list_resource_extensions(base_class=ProjectMetadataFieldExtension)
    validated = check_unique_identifiers(
        packs=packs,
        identifier_attribute="field_name",
        category_label="ProjectMetadataFieldExtension",
    )

    with _REGISTRY_LOCK:
        if _IS_FROZEN is True:
            err_msg_lines = ["Project metadata field registry is already frozen."]
            err_msg_lines.append("FROZEN_FIELDS: {}".format(sorted(_FROZEN_FIELDS.keys())))
            err_msg_lines.append("ATTEMPTED_FIELDS: {}".format(sorted(validated.keys())))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)

        _FROZEN_FIELDS.clear()
        _FROZEN_FIELDS.update(validated)
        _IS_FROZEN = True

    rtnval = dict(_FROZEN_FIELDS)
    return rtnval


def load_registered_fields() -> Dict[str, Type[ProjectMetadataFieldExtension]]:
    """
        Return a ``field_name → class`` mapping across every registered
        metadata field. When the registry is frozen the snapshot taken at
        :func:`freeze_registry` time is returned verbatim. When the
        registry is still open (tests that skip the freeze step) the set
        is recomputed on each call so extension registrations added
        mid-test are visible.

        :returns: Dict keyed by field name.
        :raises: ConfigurationError on duplicate ``field_name`` values.
    """
    with _REGISTRY_LOCK:
        if _IS_FROZEN is True:
            rtnval = dict(_FROZEN_FIELDS)
            return rtnval

    packs = list_resource_extensions(base_class=ProjectMetadataFieldExtension)
    rtnval = check_unique_identifiers(
        packs=packs,
        identifier_attribute="field_name",
        category_label="ProjectMetadataFieldExtension",
    )
    return rtnval


def is_registry_frozen() -> bool:
    """
        Return whether the registry is currently frozen.

        :returns: True when :func:`freeze_registry` has run.
    """
    with _REGISTRY_LOCK:
        rtnval = _IS_FROZEN
    return rtnval


def reset_for_testing() -> None:
    """
        Reset the frozen snapshot. Intended for the test suite only;
        production code never calls this outside test fixtures.

        :returns: None.
    """
    global _IS_FROZEN
    with _REGISTRY_LOCK:
        _FROZEN_FIELDS.clear()
        _IS_FROZEN = False
    return
