"""
.. module:: webservice.jobs.scheduling
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Minimal periodic-task scheduler shared by Layer-5/Layer-6.

.. moduleauthor:: Code Craft AI LLC

Phase-5 and Phase-6 publish a handful of recurring background tasks
(outbox publisher drain, dispatch-receipt timer-wheel tick,
reconciler scan, offline tolerance evaluators). No shared scheduler
primitive existed in the tree before PR p19b; this module provides
the minimum surface needed to register, start, and stop those tasks
at bootstrap time.

The implementation is intentionally simple — a daemon thread per
registered task on a fixed interval. A future Postgres-backed
durable scheduler (per ``0-system-health``) plugs in behind the
same :class:`PeriodicTaskScheduler` shape without changing
callers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.jobs.scheduling.scheduler import (
    PeriodicTask,
    PeriodicTaskScheduler,
    SchedulerHandle,
    default_scheduler,
    reset_default_scheduler_for_testing,
)


__all__ = [
    "PeriodicTask",
    "PeriodicTaskScheduler",
    "SchedulerHandle",
    "default_scheduler",
    "reset_default_scheduler_for_testing",
]
