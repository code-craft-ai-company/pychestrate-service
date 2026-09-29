"""
.. module:: housekeeping.tasks
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The periodic resource housekeeping tasks and their
               registration on the process-wide scheduler.

.. moduleauthor:: Code Craft AI LLC

Four tasks keep the lab's resource state moving without anyone
clicking a button:

* ``resources.reservations.activate`` turns reservations whose start
  time has arrived into allocations;
* ``resources.allocations.expire`` ends allocations that are past their
  expected check-in;
* ``resources.ip_allocations.expire`` does the same for IP address
  allocations;
* ``resources.health.run_due`` runs every enabled health check whose
  interval has elapsed, off the web request.

Each run first takes the task's lease (see :mod:`housekeeping.leases`),
so when several server processes run the scheduler only one of them
does a task's work at a time. The work runs in its own session; the
lease bookkeeping in another, so a failed run still records its outcome.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import time

from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.managers.allocation_manager import AllocationManager
from ccai.pychestrate.core.managers.audit_logger import AuditLogger
from ccai.pychestrate.core.managers.health_monitor import (
    MAX_PROBE_TIMEOUT_SECONDS,
    HealthMonitor,
)
from ccai.pychestrate.core.managers.ip_pool_manager import IPPoolManager

from ccai.pychestrate.webservice.housekeeping.leases import (
    acquire_lease,
    process_holder_id,
    release_lease,
    renew_lease,
)
from ccai.pychestrate.webservice.jobs.scheduling import (
    PeriodicTask,
    PeriodicTaskScheduler,
)


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]

# Called by a task between units of work: renews the task's lease and
# returns ``False`` when the task must stop (the lease was lost).
LeaseKeeper = Callable[[], bool]

# One run of a task's work: given its own session and a lease keeper,
# does the work and returns a one-line outcome for the lease row.
TaskWork = Callable[[DbSession, LeaseKeeper], str]


TASK_ACTIVATE_RESERVATIONS = "resources.reservations.activate"
TASK_EXPIRE_ALLOCATIONS = "resources.allocations.expire"
TASK_EXPIRE_IP_ALLOCATIONS = "resources.ip_allocations.expire"
TASK_RUN_DUE_HEALTH_CHECKS = "resources.health.run_due"

# A lease outlives any healthy run of the quick tasks by a wide margin;
# it only matters when the process holding it died mid-run.
QUICK_TASK_LEASE_SECONDS: float = 300.0

# The health task renews its lease before every probe, so the lease
# must only outlast one probe (capped at MAX_PROBE_TIMEOUT_SECONDS) plus
# the name lookup and bookkeeping around it.
HEALTH_TASK_LEASE_SECONDS: float = MAX_PROBE_TIMEOUT_SECONDS * 2 + 60.0


@dataclass(frozen=True)
class HousekeepingConfig:
    """
        How often each housekeeping task runs.

        :param reservation_activation_interval_seconds: Cadence of the
                                                        reservation
                                                        activation task.
        :param allocation_expiry_interval_seconds: Cadence of the
                                                   allocation expiry task.
        :param ip_allocation_expiry_interval_seconds: Cadence of the IP
                                                      allocation expiry
                                                      task.
        :param health_check_interval_seconds: How often the scheduler
                                              looks for due health
                                              checks; each check still
                                              runs on its own configured
                                              interval. It is also how
                                              long a person's "Run
                                              Health Check" waits before
                                              the worker picks it up.
        :param health_check_time_budget_seconds: How long one run may
                                                 keep starting probes;
                                                 checks left over wait
                                                 for the next run,
                                                 longest-waiting first.
    """
    reservation_activation_interval_seconds: float = 30.0
    allocation_expiry_interval_seconds: float = 60.0
    ip_allocation_expiry_interval_seconds: float = 60.0
    health_check_interval_seconds: float = 5.0
    health_check_time_budget_seconds: float = 60.0


def run_with_lease(
        *,
        session_factory: SessionFactory,
        task_name: str,
        ttl_seconds: float,
        work: TaskWork,
        holder_id: Optional[str] = None
    ) -> Optional[str]:
    """
        Run one task's ``work`` if this process can take the task's lease,
        then release the lease with the run's outcome. A failing run is
        rolled back and recorded as failed; it does not raise.

        :param session_factory: Opens the work and lease sessions.
        :param task_name: The housekeeping task's name.
        :param ttl_seconds: The lease's time-to-live.
        :param work: The task's work.
        :param holder_id: The lease-holder identity (defaults to this
                          process's).

        :returns: The outcome recorded on the lease, or ``None`` when
                  another process holds the lease.
    """
    if holder_id is None:
        holder_id = process_holder_id()

    rtnval: Optional[str] = None
    lease_session = session_factory()
    try:
        acquired = acquire_lease(
            lease_session, task_name=task_name, holder_id=holder_id, ttl_seconds=ttl_seconds,
        )
        if acquired is True:
            def keep_lease() -> bool:
                kept = renew_lease(
                    lease_session, task_name=task_name, holder_id=holder_id, ttl_seconds=ttl_seconds,
                )
                return kept

            work_session = session_factory()
            try:
                outcome = work(work_session, keep_lease)
            except Exception as xcpt:  # noqa: BLE001 — record the failure on the lease
                work_session.rollback()
                outcome = "failed: {}".format(xcpt)
                logger.warning("housekeeping.task_failed name=%s error=%s", task_name, xcpt)
                logger.debug("housekeeping.task_failed name=%s", task_name, exc_info=True)
            finally:
                work_session.close()

            release_lease(lease_session, task_name=task_name, holder_id=holder_id, outcome=outcome)
            rtnval = outcome
    finally:
        lease_session.close()
    return rtnval


def activate_due_reservations_work(db_session: DbSession, keep_lease: LeaseKeeper) -> str:
    """
        Turn every pending reservation whose start time has arrived into an
        allocation (when its resource is free and healthy).

        :param db_session: The work session.
        :param keep_lease: Unused; the work is one short transaction.

        :returns: The run's outcome.
    """
    manager = AllocationManager(db_session, audit_logger=AuditLogger(db_session))
    count = manager.activate_due_reservations()
    if count > 0:
        logger.info("housekeeping.reservations_activated count=%s", count)
    rtnval = "activated {} reservation(s)".format(count)
    return rtnval


def expire_allocations_work(db_session: DbSession, keep_lease: LeaseKeeper) -> str:
    """
        End every active allocation that is past its expected check-in.

        :param db_session: The work session.
        :param keep_lease: Unused; the work is one short transaction.

        :returns: The run's outcome.
    """
    manager = AllocationManager(db_session, audit_logger=AuditLogger(db_session))
    count = manager.expire_timed_out_allocations()
    if count > 0:
        logger.info("housekeeping.allocations_expired count=%s", count)
    rtnval = "expired {} allocation(s)".format(count)
    return rtnval


def expire_ip_allocations_work(db_session: DbSession, keep_lease: LeaseKeeper) -> str:
    """
        End every active IP address allocation that is past its expected
        check-in.

        :param db_session: The work session.
        :param keep_lease: Unused; the work is one short transaction.

        :returns: The run's outcome.
    """
    manager = IPPoolManager(db_session, audit_logger=AuditLogger(db_session))
    count = manager.expire_timed_out_allocations()
    if count > 0:
        logger.info("housekeeping.ip_allocations_expired count=%s", count)
    rtnval = "expired {} IP allocation(s)".format(count)
    return rtnval


def make_health_check_work(*, time_budget_seconds: float) -> TaskWork:
    """
        Build the work that runs the due health checks, longest-waiting
        first, until none are left, the time budget is spent, or the lease
        is lost.

        :param time_budget_seconds: How long the run may keep starting
                                    probes.

        :returns: The task's work.
    """
    def _work(db_session: DbSession, keep_lease: LeaseKeeper) -> str:
        deadline = time.monotonic() + time_budget_seconds

        def should_continue() -> bool:
            keep_going = time.monotonic() < deadline and keep_lease()
            return keep_going

        monitor = HealthMonitor(db_session, audit_logger=AuditLogger(db_session))
        summary = monitor.run_due_health_checks(should_continue=should_continue)
        if summary.status_changes > 0:
            logger.info(
                "housekeeping.health_checks_ran checked=%s status_changes=%s",
                summary.total_checked, summary.status_changes,
            )
        outcome = "checked {} resource(s), {} status change(s)".format(
            summary.total_checked, summary.status_changes,
        )
        return outcome

    rtnval = _work
    return rtnval


def _leased_task(
        *,
        name: str,
        interval_seconds: float,
        ttl_seconds: float,
        work: TaskWork,
        session_factory: SessionFactory,
        holder_id: Optional[str]
    ) -> PeriodicTask:
    """
        Wrap ``work`` as a :class:`PeriodicTask` that runs it under the
        task's lease on every tick.

        :returns: The periodic task.
    """
    def _tick() -> None:
        try:
            run_with_lease(
                session_factory=session_factory,
                task_name=name,
                ttl_seconds=ttl_seconds,
                work=work,
                holder_id=holder_id,
            )
        except Exception as xcpt:  # noqa: BLE001 — lease bookkeeping failed; retry next tick
            logger.warning("housekeeping.lease_failed name=%s error=%s", name, xcpt)
            logger.debug("housekeeping.lease_failed name=%s", name, exc_info=True)
        return

    rtnval = PeriodicTask(name=name, interval_seconds=interval_seconds, run=_tick)
    return rtnval


def build_housekeeping_tasks(
        *,
        session_factory: SessionFactory,
        config: Optional[HousekeepingConfig] = None,
        holder_id: Optional[str] = None
    ) -> List[PeriodicTask]:
    """
        Build the resource housekeeping tasks.

        :param session_factory: Opens a fresh session per run.
        :param config: Task cadences (defaults to :class:`HousekeepingConfig`).
        :param holder_id: Lease-holder identity (defaults to this process's;
                          tests pass one to act as several processes).

        :returns: The tasks, in registration order.
    """
    if config is None:
        config = HousekeepingConfig()

    rtnval = [
        _leased_task(
            name=TASK_ACTIVATE_RESERVATIONS,
            interval_seconds=config.reservation_activation_interval_seconds,
            ttl_seconds=QUICK_TASK_LEASE_SECONDS,
            work=activate_due_reservations_work,
            session_factory=session_factory,
            holder_id=holder_id,
        ),
        _leased_task(
            name=TASK_EXPIRE_ALLOCATIONS,
            interval_seconds=config.allocation_expiry_interval_seconds,
            ttl_seconds=QUICK_TASK_LEASE_SECONDS,
            work=expire_allocations_work,
            session_factory=session_factory,
            holder_id=holder_id,
        ),
        _leased_task(
            name=TASK_EXPIRE_IP_ALLOCATIONS,
            interval_seconds=config.ip_allocation_expiry_interval_seconds,
            ttl_seconds=QUICK_TASK_LEASE_SECONDS,
            work=expire_ip_allocations_work,
            session_factory=session_factory,
            holder_id=holder_id,
        ),
        _leased_task(
            name=TASK_RUN_DUE_HEALTH_CHECKS,
            interval_seconds=config.health_check_interval_seconds,
            ttl_seconds=HEALTH_TASK_LEASE_SECONDS,
            work=make_health_check_work(time_budget_seconds=config.health_check_time_budget_seconds),
            session_factory=session_factory,
            holder_id=holder_id,
        ),
    ]
    return rtnval


def register_housekeeping_tasks(
        *,
        scheduler: PeriodicTaskScheduler,
        session_factory: SessionFactory,
        config: Optional[HousekeepingConfig] = None
    ) -> List[str]:
    """
        Register every housekeeping task not yet on ``scheduler``. Call it
        before the scheduler starts: tasks registered after
        :meth:`PeriodicTaskScheduler.start` never run.

        :param scheduler: The scheduler to register on.
        :param session_factory: Opens a fresh session per run.
        :param config: Task cadences (defaults to :class:`HousekeepingConfig`).

        :returns: The names of the tasks registered by this call.
    """
    existing_names = set(scheduler.task_names())
    rtnval: List[str] = []
    for task in build_housekeeping_tasks(session_factory=session_factory, config=config):
        if task.name in existing_names:
            continue
        scheduler.register(task=task)
        rtnval.append(task.name)
    return rtnval
