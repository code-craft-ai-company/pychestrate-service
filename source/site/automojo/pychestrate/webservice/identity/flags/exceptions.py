"""
.. module:: identity.flags.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the feature-flags service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class FlagAlreadyExistsError(Exception):
    """
        Raised when create_flag conflicts with an existing flag_key.
    """


class FlagNotFoundError(Exception):
    """
        Raised when a lookup by flag_key returns no row.
    """


class FlagBackendUnavailableError(Exception):
    """
        Raised when the resolved backend cannot serve a request.
    """
