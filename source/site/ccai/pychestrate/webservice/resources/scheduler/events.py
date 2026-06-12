"""
.. module:: resources.scheduler.events
    :synopsis: Scheduler bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SchedulerEventTopics:
    """
        Reservation-scheduler bus topics. M1 emits ``ENQUEUED``,
        ``CANCELLED`` and ``DISPATCHED``. M2 adds the starvation
        promotion + algorithm-fallback topics.
    """
    ENQUEUED = "pychestrate.scheduler.enqueued"
    CANCELLED = "pychestrate.scheduler.cancelled"
    DISPATCHED = "pychestrate.scheduler.dispatched"
    STARVATION_PROMOTED = "pychestrate.scheduler.starvation_promoted"
    ALGORITHM_MISSING = "pychestrate.scheduler.algorithm_missing"
