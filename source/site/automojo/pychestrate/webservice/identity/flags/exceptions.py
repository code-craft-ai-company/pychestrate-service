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


class FlagKindImmutableError(Exception):
    """
        Raised when a caller attempts to change a flag's
        ``flag_kind`` after creation. The kind is part of the
        flag's identity contract — every consumer that reads
        the flag depends on its kind to decode the value.
    """


class FlagValueInvalidError(Exception):
    """
        Raised when a default_value does not match the flag's
        declared kind (e.g. a STRING flag receiving a list,
        an ENUM flag receiving a value outside the declared
        choices).
    """


class FlagAlreadyRetiredError(Exception):
    """
        Raised when a caller attempts a retirement operation
        on a flag that is already past ACTIVE.
    """
