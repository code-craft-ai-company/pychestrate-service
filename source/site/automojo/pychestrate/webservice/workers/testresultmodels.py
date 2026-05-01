"""
.. module:: workers.testresultmodels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM model for first-class test results.

.. moduleauthor:: Automation Mojo LLC

A :class:`WorkerJobTestResult` row is one assertion-level
result produced by a test running inside a worker job —
``passed`` / ``failed`` / ``skipped`` / ``errored`` plus the
failure message + traceback when relevant.

Pychestrate is a testing service. Until now, the only signal a
flow could check was the subprocess exit code on a
:class:`WorkerJob` row, which conflates "the test runner crashed
before getting going" with "the third assertion in the suite
failed but the rest passed". This table keeps that signal as
data: a runner emits one row per case, so the dashboard can
render pass/fail counts, the failure trace can be read directly
without scraping stdout, and a flake-rate detector can run
queries against history.
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


class TestOutcome(str, enum.Enum):
    """
        Conventional outcome values. The column is a
        ``String``, not an enum constraint, for forward compat
        — a runner that needs ``xfailed`` / ``xpassed`` /
        ``unknown`` can use whatever name the operator chose.
    """
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERRORED = "errored"


class WorkerJobTestResult(PychestratePhase1Base):
    """
        One assertion-level test result for a worker job.

        :ivar result_id: Server-issued primary key.
        :ivar job_id: FK to ``worker_jobs.job_id``.
        :ivar worker_id: FK to ``workers.worker_id``. Nullable so
                         the row survives worker deregistration.
        :ivar attempt: Which attempt of the job produced this
                       result, 1-indexed. Lets retried jobs
                       compare flake rates between attempts.
        :ivar suite_name: Operator-meaningful suite grouping
                          (e.g. ``smoke``, ``hardware``).
        :ivar case_name: Test case identifier (e.g.
                         ``test_login_with_valid_credentials``).
        :ivar outcome: ``passed`` / ``failed`` / ``skipped`` /
                       ``errored`` (or any operator-defined
                       value).
        :ivar duration_seconds: Wall-clock duration the runner
                                reported.
        :ivar started_at: When the case started running.
        :ivar completed_at: When the case finished (terminal).
        :ivar failure_message: Short failure summary
                               (one-liner the dashboard shows).
        :ivar failure_trace: Full traceback / failure detail.
        :ivar attributes: Free-form JSON for runner-specific
                          metadata (browser, build commit,
                          tags, etc.).
    """

    __tablename__ = "worker_job_test_results"
    __table_args__ = (
        Index("ix_worker_job_test_results_job_id", "job_id"),
        Index("ix_worker_job_test_results_outcome", "outcome"),
        Index(
            "ix_worker_job_test_results_suite_case",
            "suite_name", "case_name",
        ),
    )

    result_id = Column(UUIDType(binary=False), primary_key=True)
    job_id = Column(
        UUIDType(binary=False),
        ForeignKey("worker_jobs.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    worker_id = Column(
        UUIDType(binary=False),
        ForeignKey("workers.worker_id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt = Column(Integer, nullable=False, default=1)
    suite_name = Column(String(255), nullable=False, default="")
    case_name = Column(String(512), nullable=False)
    outcome = Column(String(32), nullable=False)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    failure_message = Column(Text, nullable=True)
    failure_trace = Column(Text, nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
