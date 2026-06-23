"""
.. module:: resources.scheduler.errors
    :synopsis: Scheduler exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SchedulerError(Exception):
    """
        Base for recoverable scheduler errors.
    """


class SchedulerEntryNotFoundError(SchedulerError):
    """
        Raised when an entry lookup misses.
    """


class SchedulerEntryConflictError(SchedulerError):
    """
        Raised when an entry already exists for the supplied
        reservation. Enqueue is a 1:1 reservation-to-entry op.
    """


class SchedulerUnavailableError(SchedulerError):
    """
        Raised when the scheduler refuses an enqueue — e.g. the
        service is in maintenance drain. M2 wires the drain
        signal; M1 reserves the type for callers to surface.
    """


class SchedulerAspectsInvalidError(SchedulerError):
    """
        Raised when caller-supplied :class:`SchedulerAspects`
        violates the normalization rules. The message names the
        offending field.
    """
