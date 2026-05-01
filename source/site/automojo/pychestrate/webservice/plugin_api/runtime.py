"""
.. module:: plugin_api.runtime
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local cache of the published-surface catalog.

.. moduleauthor:: Automation Mojo LLC

The catalog is derived from class annotations at startup and cached
for the process lifetime per NFR-4. Build is always paired with
validate; a corrupted annotation causes a loud startup failure rather
than a silently-empty catalog.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from typing import Optional

from automojo.pychestrate.webservice.plugin_api.catalog_builder import (
    Catalog,
    build_catalog,
)
from automojo.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)


_LOCK = threading.RLock()
_ACTIVE_CATALOG: Optional[Catalog] = None


def build_and_validate_catalog() -> Catalog:
    """
        Build the catalog, validate every reference, and cache the
        result for subsequent :func:`get_active_catalog` calls.

        :returns: The newly cached :class:`Catalog`.
        :raises: ConfigurationError on any unresolved reference.
    """
    global _ACTIVE_CATALOG
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    with _LOCK:
        _ACTIVE_CATALOG = catalog
    rtnval = catalog
    return rtnval


def get_active_catalog() -> Catalog:
    """
        Return the cached catalog. If no catalog has been built yet,
        builds one on demand.

        :returns: Cached :class:`Catalog`.
    """
    global _ACTIVE_CATALOG
    with _LOCK:
        cached = _ACTIVE_CATALOG
    if cached is not None:
        rtnval = cached
        return rtnval
    rtnval = build_and_validate_catalog()
    return rtnval


def reset_for_testing() -> None:
    """
        Clear the cached catalog. Test helper.

        :returns: None.
    """
    global _ACTIVE_CATALOG
    with _LOCK:
        _ACTIVE_CATALOG = None
    return
