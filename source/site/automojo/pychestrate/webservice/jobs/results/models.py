"""
.. module:: jobs.results.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for shared-results allocation rows.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class SharedResultsAllocation(PychestratePhase1Base, SerializableModel):
    """
        One row per dispatched run captures the allocated path on
        the shared object store. Allocate-on-conflict-do-nothing
        keeps reissues idempotent: a re-dispatch of the same run
        re-reads the existing prefix instead of creating a parallel
        path.
    """

    __tablename__ = "jobs_shared_results_allocation"

    allocation_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    backend_driver = Column(String(64), nullable=False, default="")
    backend_key_prefix = Column(String(512), nullable=False, default="")
    allocated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_jobs_shared_results_allocation_run",
        ),
        Index(
            "ix_jobs_shared_results_allocation_project_id",
            "project_id",
        ),
    )
