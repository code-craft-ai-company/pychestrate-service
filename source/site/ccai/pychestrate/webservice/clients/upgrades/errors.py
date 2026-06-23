"""
.. module:: clients.upgrades.errors
    :synopsis: 3-agent-upgrade-channel exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.errors.exceptions import SemanticError


class UpgradeError(Exception):
    """
        Base for recoverable upgrade-channel errors.
    """


class RolloutNotFoundError(UpgradeError):
    """
        Raised when a rollout-id lookup misses.
    """


class PinConflictError(UpgradeError):
    """
        Raised when a pin is set to a version that is unknown
        to any rollout (defensive check). M1 still allows pin
        rows to point at any string version; the safety check
        runs at offer-set computation time.
    """


class InvalidRolloutTransitionError(SemanticError):
    """
        Raised on an illegal state-machine transition (e.g.,
        starting a rollout that is already ACTIVE). Inherits
        :class:`SemanticError` so it bubbles per AGENTS.md.
    """
