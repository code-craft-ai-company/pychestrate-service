"""
.. module:: orchestration.test.catalog.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the test catalog.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class CatalogError(Exception):
    """
        Base for recoverable catalog errors.
    """


class CatalogEntryNotFoundError(CatalogError):
    """
        Raised when a lookup against the catalog finds no row or
        when a referenced entry has been retired.
    """
