"""
.. module:: resources.checkout
    :synopsis: 4-checkout-checkin — reservation lifecycle.

Public surface:

* :class:`Reservation`, :class:`ReservationMode`,
  :class:`ReservationState` — persistence row + enums.
* :class:`ReservationView`, :class:`ReservationAspects`.
* :func:`reserve`, :func:`release`, :func:`get_reservation`,
  :func:`list_reservations_for_resource`.
* :class:`ReservationEventTopics`.
* Errors: :class:`ReservationError`,
  :class:`ReservationConflictError`,
  :class:`ReservationNotFoundError`,
  :class:`ReservationStateError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.resources.checkout.errors import (
    ReservationConflictError,
    ReservationError,
    ReservationNotFoundError,
    ReservationStateError,
)
from ccai.pychestrate.webservice.resources.checkout.events import (
    ReservationEventTopics,
)
from ccai.pychestrate.webservice.resources.checkout.models import (
    Reservation,
    ReservationMode,
    ReservationState,
)
from ccai.pychestrate.webservice.resources.checkout.service import (
    ReservationAspects,
    ReservationView,
    get_reservation,
    list_reservations_for_resource,
    release,
    reserve,
)
