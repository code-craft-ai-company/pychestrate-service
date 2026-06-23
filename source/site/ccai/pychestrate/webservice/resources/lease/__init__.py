"""
.. module:: resources.lease
    :synopsis: 4-lease-heartbeat — TTL leases on granted reservations.

Public surface:

* :class:`Lease`, :class:`LeaseState` — persistence row + enum.
* :class:`LeaseAspects`, :class:`LeaseView` — IO shapes.
* :func:`attach_lease`, :func:`heartbeat`,
  :func:`release_lease`, :func:`sweep_expired`,
  :func:`get_lease`, :func:`get_lease_for_reservation`.
* :class:`LeaseEventTopics`.
* Errors: :class:`LeaseError`, :class:`LeaseNotFoundError`,
  :class:`LeaseStateError`, :class:`LeaseAspectsInvalidError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.resources.lease.errors import (
    LeaseAspectsInvalidError,
    LeaseError,
    LeaseNotFoundError,
    LeaseStateError,
)
from ccai.pychestrate.webservice.resources.lease.events import (
    LeaseEventTopics,
)
from ccai.pychestrate.webservice.resources.lease.models import (
    Lease,
    LeaseState,
)
from ccai.pychestrate.webservice.resources.lease.service import (
    LeaseAspects,
    LeaseView,
    attach_lease,
    get_lease,
    get_lease_for_reservation,
    heartbeat,
    release_lease,
    sweep_expired,
)
