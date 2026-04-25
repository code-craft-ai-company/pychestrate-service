"""
.. module:: orchestration.test.flake.errors
    :synopsis: Flake-tracking exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class FlakeError(Exception):
    """
        Base for recoverable flake-tracking errors.
    """


class FlakeClassificationNotFoundError(FlakeError):
    """
        Raised when a classification lookup misses.
    """


class FlakeClassifierNotFoundError(FlakeError):
    """
        Raised when no classifier is registered (or the named
        classifier cannot be resolved).
    """


class OutcomeIdentityInvalidError(FlakeError):
    """
        Raised on empty / oversized raw test-case identities.
    """
