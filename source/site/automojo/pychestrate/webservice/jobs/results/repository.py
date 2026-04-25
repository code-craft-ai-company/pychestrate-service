"""
.. module:: jobs.results.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: AllocationRepository — persistence helpers for the shared backend.

.. moduleauthor:: Automation Mojo LLC

Idempotent insert is implemented at the service layer
(:class:`SharedResultsBackend.allocate`) via lookup-then-insert
because that pattern stays portable across SQLite tests and the
Postgres production target. The unique constraint on ``run_id``
guards the invariant at the DB level either way.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.jobs.results.models import (
    SharedResultsAllocation,
)


def find_by_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[SharedResultsAllocation]:
    """
        Fetch the allocation row for ``run_id``.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: Row or ``None``.
    """
    rtnval = (
        db_session.query(SharedResultsAllocation)
        .filter(SharedResultsAllocation.run_id == run_id)
        .first()
    )
    return rtnval


def insert_allocation(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        backend_driver: str,
        backend_key_prefix: str,
        allocated_at: datetime
    ) -> SharedResultsAllocation:
    """
        Insert a fresh allocation row.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param backend_driver: Driver name (``"smb"``, ``"s3"``,
                               …).
        :param backend_key_prefix: Canonical prefix the run will
                                   write its result tree under.
        :param allocated_at: Commit timestamp.

        :returns: Persisted row.
    """
    row = SharedResultsAllocation(
        allocation_id=new_uuid(),
        run_id=run_id,
        project_id=project_id,
        backend_driver=backend_driver,
        backend_key_prefix=backend_key_prefix,
        allocated_at=allocated_at,
    )
    db_session.add(row)
    db_session.flush()
    return row
