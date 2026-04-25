"""
.. module:: jobs.results.backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SharedResultsBackend — allocate + resolve facade.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.jobs.results import repository
from automojo.pychestrate.webservice.jobs.results.errors import (
    AllocationNotFoundError,
)
from automojo.pychestrate.webservice.jobs.results.path_builder import (
    build_canonical_prefix,
)


@dataclass(frozen=True)
class AllocatedResultPath:
    """
        Read-model returned to callers. Stable across releases so
        downstream features bind to this shape rather than the ORM
        row.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param backend_driver: Object-store driver name.
        :param backend_key_prefix: Canonical prefix.
        :param allocated_at: Allocation timestamp.
    """
    run_id: str
    project_id: str
    backend_driver: str
    backend_key_prefix: str
    allocated_at: datetime


class SharedResultsBackend:
    """
        Per-run path allocator backed by ``jobs_shared_results_allocation``.
        ``allocate`` is idempotent on ``run_id`` so re-dispatch does
        not fork the path.
    """

    def __init__(self, *, backend_driver: str) -> None:
        """
            :param backend_driver: Driver name persisted on every
                                   allocation row. Resolves through
                                   the ``object_store_driver``
                                   factory at the storage layer.
        """
        self._backend_driver: str = backend_driver
        return

    def backend_driver(self) -> str:
        """
            Return the configured driver name.

            :returns: Driver string.
        """
        rtnval = self._backend_driver
        return rtnval

    def allocate(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            project_slug: str,
            job_type: str,
            now: Optional[datetime] = None
        ) -> AllocatedResultPath:
        """
            Return the per-run allocated prefix, inserting a fresh
            row when none exists.

            :param db_session: Active SQLAlchemy session.
            :param run_id: Run UUID.
            :param project_id: Owning project UUID.
            :param project_slug: Project slug (sanitized into the
                                 path).
            :param job_type: Job-type string (sanitized into the
                             path).
            :param now: Optional override for the allocation
                        timestamp.

            :returns: :class:`AllocatedResultPath`.
        """
        existing = repository.find_by_run(
            db_session=db_session, run_id=run_id,
        )
        if existing is not None:
            rtnval = _to_record(row=existing)
            return rtnval

        allocated_at = now
        if allocated_at is None:
            allocated_at = utc_now()
        prefix = build_canonical_prefix(
            project_slug=project_slug,
            job_type=job_type,
            run_id=run_id,
            when=allocated_at,
        )
        row = repository.insert_allocation(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            backend_driver=self._backend_driver,
            backend_key_prefix=prefix,
            allocated_at=allocated_at,
        )
        db_session.commit()
        rtnval = _to_record(row=row)
        return rtnval

    def resolve(
            self,
            *,
            db_session: DbSession,
            run_id: str
        ) -> AllocatedResultPath:
        """
            Look up an existing allocation. Used by the result
            watcher to find the prefix to poll.

            :param db_session: Active SQLAlchemy session.
            :param run_id: Run UUID.

            :returns: :class:`AllocatedResultPath`.
            :raises: AllocationNotFoundError when no row exists.
        """
        existing = repository.find_by_run(
            db_session=db_session, run_id=run_id,
        )
        if existing is None:
            err_lines = ["Shared-results allocation not found."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_msg = os.linesep.join(err_lines)
            raise AllocationNotFoundError(err_msg) from None
        rtnval = _to_record(row=existing)
        return rtnval


def _to_record(*, row) -> AllocatedResultPath:
    """
        Convert an ORM row to the read model.

        :param row: ``SharedResultsAllocation``.

        :returns: :class:`AllocatedResultPath`.
    """
    rtnval = AllocatedResultPath(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        backend_driver=row.backend_driver,
        backend_key_prefix=row.backend_key_prefix,
        allocated_at=row.allocated_at,
    )
    return rtnval
