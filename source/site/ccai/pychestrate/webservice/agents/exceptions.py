"""
.. module:: agents.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by Layer-3 agent services.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class FrameValidationError(Exception):
    """
        Raised by the agent-protocol frame validator.
    """


class SessionClosedError(Exception):
    """
        Raised when an operation targets a closed client session.
    """


class CapabilityRejectedError(Exception):
    """
        Raised when a capability value violates the declared schema.
    """


class UnknownCapabilityKindError(Exception):
    """
        Raised when a capability references an unregistered kind.
    """


class RolloutNotFoundError(Exception):
    """
        Raised when a rollout lookup has no match.
    """


class RolloutStateTransitionError(Exception):
    """
        Raised when an invalid rollout transition is attempted.
    """
