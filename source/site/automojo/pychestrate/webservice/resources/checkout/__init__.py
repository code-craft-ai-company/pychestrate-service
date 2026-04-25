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

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.resources.checkout.errors import (
    ReservationConflictError,
    ReservationError,
    ReservationNotFoundError,
    ReservationStateError,
)
from automojo.pychestrate.webservice.resources.checkout.events import (
    ReservationEventTopics,
)
from automojo.pychestrate.webservice.resources.checkout.models import (
    Reservation,
    ReservationMode,
    ReservationState,
)
from automojo.pychestrate.webservice.resources.checkout.service import (
    ReservationAspects,
    ReservationView,
    get_reservation,
    list_reservations_for_resource,
    release,
    reserve,
)
