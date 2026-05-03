"""
.. module:: persistence.exceptions
    :synopsis: Persistence layer exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.errors.exceptions import SemanticError


class PersistenceError(Exception):
    """
        Base for recoverable persistence-layer errors.
    """


class StaleEntityError(PersistenceError):
    """
        Raised when a save() targeting an explicit version
        loses the optimistic-concurrency race — the row's
        version was bumped by a concurrent writer between the
        load and the save.
    """


class EntityNotFoundError(PersistenceError):
    """
        Raised when a delete() against an unknown id is asked
        to fail loudly. The default
        :meth:`Repository.delete` returns ``False`` instead.
    """


class UnitOfWorkMisuseError(SemanticError):
    """
        Raised when a caller misuses the
        :func:`unit_of_work` context manager (commits inside a
        nested savepoint, exits without closing the session,
        etc.). Inherits :class:`SemanticError` so it bubbles
        per AGENTS.md.
    """
