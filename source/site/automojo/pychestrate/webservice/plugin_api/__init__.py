"""
.. module:: webservice.plugin_api
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Externally-stable subset of Pychestrate's Layer E surface.

.. moduleauthor:: Automation Mojo LLC

This package implements ``8-plugin-api`` / ``E-plugin-api`` — the
catalogued, frozen subset of factory protocols and resource extension
bases that external ``pychestrate-ext-<name>`` packages target. M1
ships the catalog builder, the validator, and the read-only REST
endpoint. M2 layers in the load-policy evaluator that gates extension
loads on the published surface.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.plugin_api.annotations import (
    PUBLISHED_STATUS_DEPRECATED,
    PUBLISHED_STATUS_REMOVED_IN_NEXT_MAJOR,
    PUBLISHED_STATUS_SUPPORTED,
    PublishedSurfaceMetadata,
    extract_published_metadata,
    is_class_published,
)
from automojo.pychestrate.webservice.plugin_api.catalog_builder import (
    CatalogEntry,
    build_catalog,
    catalog_to_jsonable,
)
from automojo.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)


__all__ = [
    "PUBLISHED_STATUS_DEPRECATED",
    "PUBLISHED_STATUS_REMOVED_IN_NEXT_MAJOR",
    "PUBLISHED_STATUS_SUPPORTED",
    "PublishedSurfaceMetadata",
    "CatalogEntry",
    "extract_published_metadata",
    "is_class_published",
    "build_catalog",
    "catalog_to_jsonable",
    "validate_catalog_against_code",
]
