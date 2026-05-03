"""
.. module:: persistence.uow
    :synopsis: unit_of_work context manager with savepoint support.

The unit-of-work helper wraps a SQLAlchemy session in an
explicit transaction boundary. Nested ``with`` blocks open
SAVEPOINTs so partial work can roll back without aborting the
outer transaction.

The contract:

* The outermost ``with`` block opens a transaction. On a clean
  exit, ``commit()`` runs against the session. On an exception,
  ``rollback()`` runs and the exception bubbles.
* A nested ``with`` block opens a SAVEPOINT. On a clean exit,
  the savepoint is released; on exception, the savepoint
  rolls back without aborting the outer transaction.
* Calling ``session.commit()`` inside a nested savepoint
  raises :class:`UnitOfWorkMisuseError` — the spec requires
  the inner block to be transparent to the outer transaction.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.persistence.exceptions import (
    UnitOfWorkMisuseError,
)


_DEPTH_LOCK = threading.Lock()
_DEPTH_BY_SESSION: dict = {}


def _depth_for(session: DbSession) -> int:
    with _DEPTH_LOCK:
        return _DEPTH_BY_SESSION.get(id(session), 0)


def _bump_depth(session: DbSession, *, delta: int) -> int:
    with _DEPTH_LOCK:
        current = _DEPTH_BY_SESSION.get(id(session), 0)
        new_value = current + delta
        if new_value <= 0:
            _DEPTH_BY_SESSION.pop(id(session), None)
        else:
            _DEPTH_BY_SESSION[id(session)] = new_value
        return new_value


@contextmanager
def unit_of_work(*, db_session: DbSession) -> Iterator[DbSession]:
    """
        Open a unit-of-work transaction or a nested savepoint
        depending on whether one is already active for this
        session.

        :param db_session: Active SQLAlchemy session.

        :raises: UnitOfWorkMisuseError when a caller commits
                 the session inside a nested savepoint.
    """
    starting_depth = _depth_for(db_session)
    if starting_depth == 0:
        _bump_depth(db_session, delta=1)
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            _bump_depth(db_session, delta=-1)
            raise
        else:
            try:
                db_session.commit()
            finally:
                _bump_depth(db_session, delta=-1)
        return

    # Nested savepoint path.
    savepoint = db_session.begin_nested()
    _bump_depth(db_session, delta=1)
    pre_state_active = savepoint.is_active
    try:
        yield db_session
    except Exception:
        if savepoint.is_active is True:
            savepoint.rollback()
        _bump_depth(db_session, delta=-1)
        raise
    else:
        if savepoint.is_active is False and pre_state_active is True:
            # The body called commit() and dropped the savepoint
            # — that's the misuse case.
            _bump_depth(db_session, delta=-1)
            err_lines = [
                "unit_of_work nested block must not commit the session.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise UnitOfWorkMisuseError(err_msg) from None
        try:
            if savepoint.is_active is True:
                savepoint.commit()
        finally:
            _bump_depth(db_session, delta=-1)
    return


def reset_for_testing() -> None:
    """
        Drop the per-session depth tracker. Tests use this to
        keep the module-level state from leaking across
        cases.
    """
    with _DEPTH_LOCK:
        _DEPTH_BY_SESSION.clear()
    return
