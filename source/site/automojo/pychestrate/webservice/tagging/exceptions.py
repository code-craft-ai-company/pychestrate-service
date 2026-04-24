"""
.. module:: tagging.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-tagging service APIs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class TaxonomyNotFoundError(Exception):
    """
        Raised when a referenced taxonomy is not registered.
    """


class TagValueValidationError(Exception):
    """
        Raised when a tag value fails taxonomy validation.
    """


class TagAssignmentNotFoundError(Exception):
    """
        Raised when removing a tag that was never assigned.
    """
