"""
.. module:: jobs.results.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types for the shared-results backend.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SharedResultsError(Exception):
    """
        Base class for shared-results backend errors.
    """


class AllocationNotFoundError(SharedResultsError):
    """
        Raised by :meth:`SharedResultsBackend.resolve` when no
        allocation row exists for the given run id.
    """


class PathComponentInvalidError(SharedResultsError):
    """
        Raised by :func:`canonicalize_component` when a component
        cannot be sanitized into a safe filesystem segment (empty
        after sanitization, or excessively long).
    """
