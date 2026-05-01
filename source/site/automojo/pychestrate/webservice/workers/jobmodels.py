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
    Float,
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


class RetryStrategy(str, enum.Enum):
    """
        How the queue computes the delay before re-enqueuing a
        failed attempt.

        * ``FIXED`` — every retry waits exactly
          ``retry_delay_seconds`` after the failed attempt.
        * ``EXPONENTIAL`` — the delay doubles each attempt:
          ``retry_delay_seconds * 2**(attempt - 1)``. Useful for
          flaky network targets where a brief blip should be
          retried fast but a sustained outage shouldn't hammer
          the worker.
    """
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


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
        :ivar attempt: Which attempt this is, 1-indexed. Bumped
                       by ``report_result`` (and the stale-worker
                       sweeper) when a failed attempt is
                       re-enqueued under a retry policy.
        :ivar max_attempts: Total attempts the queue is allowed
                            to schedule for this job. ``1`` means
                            "no retries"; ``3`` means "two
                            retries on failure".
        :ivar retry_delay_seconds: Base delay between attempts.
                                   The strategy below decides how
                                   the delay grows with attempts.
        :ivar retry_strategy: One of :class:`RetryStrategy`.
        :ivar not_before: When set, ``claim_next_job`` must skip
                          this row until ``now >= not_before``.
                          Used to schedule the next retry's
                          earliest claim time.
        :ivar required_capabilities: List of capability strings
                                     the worker must advertise in
                                     ``attributes.capabilities``
                                     to be allowed to claim this
                                     job. Empty list means
                                     "any worker".
        :ivar lease_holder: When set, ``claim_next_job`` will
                            only let workers that are either
                            unleased OR leased to this same
                            holder claim the job. On successful
                            claim the worker's lease is acquired
                            (or extended) for ``lease_holder``
                            with TTL ``lease_ttl_seconds``.
                            Typically set by ``RemoteCommand``
                            with ``exclusive: true`` to the
                            owning ``flow_id``.
        :ivar lease_ttl_seconds: TTL applied at acquire / extend
                                 time. ``None`` means
                                 "don't acquire a lease on
                                 claim".
        :ivar priority: Higher = claimed sooner. Default ``0``.
                        Negative values run after default-priority
                        rows; positive values jump ahead. Within
                        the same priority bucket the queue is
                        FIFO by ``enqueued_at``.
        :ivar project_id: When set, only workers in the same
                          project (or globally-scoped workers
                          with no project_id) can claim this
                          job. ``None`` means "global queue —
                          any worker may claim". The matching
                          rule is symmetric on the worker side
                          too: a project-scoped worker only
                          claims jobs from its own project or
                          unscoped jobs.
    """

    __tablename__ = "worker_jobs"
    __table_args__ = (
        Index("ix_worker_jobs_state", "state"),
        Index("ix_worker_jobs_target", "target_pod_name", "target_kind"),
        Index("ix_worker_jobs_not_before", "not_before"),
        Index("ix_worker_jobs_priority", "priority"),
        Index("ix_worker_jobs_project_id", "project_id"),
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
    attempt = Column(Integer, nullable=False, default=1)
    max_attempts = Column(Integer, nullable=False, default=1)
    retry_delay_seconds = Column(Float, nullable=False, default=0.0)
    retry_strategy = Column(
        String(32), nullable=False, default=RetryStrategy.FIXED.value,
    )
    not_before = Column(DateTime(timezone=True), nullable=True)
    required_capabilities = Column(JSON, nullable=False, default=list)
    lease_holder = Column(String(255), nullable=True)
    lease_ttl_seconds = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    project_id = Column(UUIDType(binary=False), nullable=True)
