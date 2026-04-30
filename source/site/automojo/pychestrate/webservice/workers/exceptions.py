"""
.. module:: workers.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Worker-registry exception types.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class WorkerError(Exception):
    """
        Base class for worker-registry errors.
    """


class WorkerNotFoundError(WorkerError):
    """
        Raised when a worker_id has no row.
    """


class WorkerAlreadyRegisteredError(WorkerError):
    """
        Raised when (project_id, name) already exists at register time.
    """


class WorkerStateTransitionError(WorkerError):
    """
        Raised when a state change is rejected (e.g. drain -> idle).
    """
