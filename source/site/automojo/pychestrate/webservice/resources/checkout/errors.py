"""
.. module:: resources.checkout.errors
    :synopsis: Reservation exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ReservationError(Exception):
    """
        Base for recoverable reservation errors.
    """


class ReservationConflictError(ReservationError):
    """
        Raised when conflict-deconfliction rules reject a reserve
        attempt. The message names the rule that vetoed.
    """


class ReservationNotFoundError(ReservationError):
    """
        Raised when a lookup misses.
    """


class ReservationStateError(ReservationError):
    """
        Raised when a release / state transition is requested
        against a reservation that is not in a valid prior state.
    """
