"""
.. module:: resources.scheduler
    :synopsis: 4-reservation-scheduler — pool-aware reservation queue.

Public surface:

* :class:`SchedulerEntry`, :class:`SchedulerEntryState` — persistence
  row + enum.
* :class:`SchedulerAspects`, :class:`SchedulerEntryView` — IO shapes.
* :func:`enqueue`, :func:`cancel`, :func:`pick_next_for_pool`,
  :func:`mark_dispatched`, :func:`get_entry`,
  :func:`list_queued_for_pool`.
* :class:`SchedulerEventTopics`.
* Errors: :class:`SchedulerError`,
  :class:`SchedulerEntryNotFoundError`,
  :class:`SchedulerUnavailableError`,
  :class:`SchedulerAspectsInvalidError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.resources.scheduler.errors import (
    SchedulerAspectsInvalidError,
    SchedulerEntryConflictError,
    SchedulerEntryNotFoundError,
    SchedulerError,
    SchedulerUnavailableError,
)
from ccai.pychestrate.webservice.resources.scheduler.events import (
    SchedulerEventTopics,
)
from ccai.pychestrate.webservice.resources.scheduler.models import (
    SchedulerEntry,
    SchedulerEntryState,
)
from ccai.pychestrate.webservice.resources.scheduler.service import (
    SchedulerAspects,
    SchedulerEntryView,
    cancel,
    enqueue,
    get_entry,
    list_queued_for_pool,
    mark_dispatched,
    pick_next_for_pool,
)
