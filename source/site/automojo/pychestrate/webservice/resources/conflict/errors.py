"""
.. module:: resources.conflict.errors
    :synopsis: Conflict-evaluation exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ConflictError(Exception):
    """
        Base for recoverable conflict-evaluation errors.
    """
