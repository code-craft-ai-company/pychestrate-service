"""
.. module:: ingest.result.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the result ingester.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ResultIngestError(Exception):
    """
        Base class for recoverable result-ingest errors.
    """


class ResultTreeNotFoundError(ResultIngestError):
    """
        Raised when a scan target is missing on the shared backend.
    """


class ResultTreeFormatError(ResultIngestError):
    """
        Raised when a parser rejects the structure of the tree
        (missing required files, unparseable summary).
    """
