"""
.. module:: resources.checkout.events
    :synopsis: Reservation bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ReservationEventTopics:
    """
        Reservation bus topics.
    """
    CREATED = "entity.reservation.created"
    GRANTED = "entity.reservation.granted"
    RELEASED = "entity.reservation.released"
    FORCED_RELEASED = "entity.reservation.forced_released"
    CONFLICT_REJECTED = "entity.reservation.conflict_rejected"
