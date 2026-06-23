"""
.. module:: orchestration.infra.drift.errors
    :synopsis: Drift-detection exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class DriftError(Exception):
    """
        Base for recoverable drift-detection errors.
    """


class DriftScheduleNotFoundError(DriftError):
    """
        Raised when a schedule lookup misses.
    """


class DriftRunNotFoundError(DriftError):
    """
        Raised when a drift-run lookup misses.
    """


class DriftCheckerUnknownError(DriftError):
    """
        Raised when ``set_schedule`` references a checker_name
        with no registered factory.
    """


class DriftScheduleInvalidError(DriftError):
    """
        Raised when caller-supplied schedule fields fail
        validation.
    """


class DriftTickAlreadyRecordedError(DriftError):
    """
        Raised when ``record_tick`` is called twice for the
        same (project, environment, scheduled_for) tuple. The
        ledger PK guarantees exactly-once dispatch.
    """
