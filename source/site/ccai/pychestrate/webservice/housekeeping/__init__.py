"""
.. module:: housekeeping
    :synopsis: Periodic resource housekeeping: reservation activation,
               allocation expiry and scheduled health checks.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`HousekeepingLease` -- the per-task lease row.
* :func:`acquire_lease`, :func:`renew_lease`, :func:`release_lease`,
  :func:`process_holder_id` -- lease bookkeeping.
* :class:`HousekeepingConfig`, :func:`build_housekeeping_tasks`,
  :func:`register_housekeeping_tasks`, :func:`run_with_lease` -- the
  tasks and their registration on the process-wide scheduler.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.housekeeping.models import HousekeepingLease
from ccai.pychestrate.webservice.housekeeping.leases import (
    acquire_lease,
    process_holder_id,
    release_lease,
    renew_lease,
)
from ccai.pychestrate.webservice.housekeeping.tasks import (
    TASK_ACTIVATE_RESERVATIONS,
    TASK_EXPIRE_ALLOCATIONS,
    TASK_EXPIRE_IP_ALLOCATIONS,
    TASK_RUN_DUE_HEALTH_CHECKS,
    HousekeepingConfig,
    build_housekeeping_tasks,
    register_housekeeping_tasks,
    run_with_lease,
)


__all__ = [
    "HousekeepingLease",
    "acquire_lease",
    "process_holder_id",
    "release_lease",
    "renew_lease",
    "TASK_ACTIVATE_RESERVATIONS",
    "TASK_EXPIRE_ALLOCATIONS",
    "TASK_EXPIRE_IP_ALLOCATIONS",
    "TASK_RUN_DUE_HEALTH_CHECKS",
    "HousekeepingConfig",
    "build_housekeeping_tasks",
    "register_housekeeping_tasks",
    "run_with_lease",
]
