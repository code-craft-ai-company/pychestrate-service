"""
.. module:: workers.jobmodels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM model for the worker-job queue.

.. moduleauthor:: Automation Mojo LLC

A :class:`WorkerJob` row represents a unit of work submitted by the
service for a worker to execute. Jobs are claimed by workers via
:func:`claim_next_job` (workers/jobservice.py) and report results via
:func:`report_result`. The simplest job today is a shell command;
the model is intentionally generic (``payload`` is JSON) so future
job kinds can land without schema churn.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy_utils import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


class JobState(str, enum.Enum):
    """
        Lifecycle of a :class:`WorkerJob`.
    """
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkerJob(PychestratePhase1Base):
    """
        Worker-job queue row.

        :ivar job_id: Server-issued primary key.
        :ivar kind: Job kind discriminator (``run-command`` is the
                    only one shipped today).
        :ivar payload: Job-kind-specific payload (e.g. ``{command:
                       "echo hello"}`` for ``run-command``).
        :ivar target_pod_name: Optional pod-name selector. The
                               dispatcher picks an idle worker
                               whose ``pod_name`` matches; ``None``
                               means any worker.
        :ivar target_kind: Optional :class:`WorkerKind` selector.
        :ivar worker_id: FK to the worker that claimed the job.
                          Null while ``state == PENDING``.
        :ivar state: Current :class:`JobState`.
        :ivar enqueued_at: When the row was created.
        :ivar claimed_at: When a worker claimed it.
        :ivar completed_at: When the worker reported a terminal
                            result.
        :ivar result_code: Worker-reported exit code.
        :ivar stdout: Captured stdout.
        :ivar stderr: Captured stderr.
        :ivar error_text: Worker-reported error message, when the
                          worker crashed before it could report a
                          clean code.
    """

    __tablename__ = "worker_jobs"
    __table_args__ = (
        Index("ix_worker_jobs_state", "state"),
        Index("ix_worker_jobs_target", "target_pod_name", "target_kind"),
    )

    job_id = Column(UUIDType(binary=False), primary_key=True)
    kind = Column(String(64), nullable=False, default="run-command")
    payload = Column(JSON, nullable=False, default=dict)
    target_pod_name = Column(String(255), nullable=True)
    target_kind = Column(String(32), nullable=True)
    worker_id = Column(
        UUIDType(binary=False),
        ForeignKey("workers.worker_id", ondelete="SET NULL"),
        nullable=True,
    )
    state = Column(String(32), nullable=False, default=JobState.PENDING.value)
    enqueued_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=False, default="")
    stderr = Column(Text, nullable=False, default="")
    error_text = Column(Text, nullable=True)
