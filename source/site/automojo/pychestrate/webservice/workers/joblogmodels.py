"""
.. module:: workers.joblogmodels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM model for live job log chunks.

.. moduleauthor:: Automation Mojo LLC

A :class:`WorkerJobLogChunk` row holds an append-only fragment
of a running job's stdout / stderr / structured log line. The
final ``stdout`` / ``stderr`` columns on :class:`WorkerJob` are
the snapshot at terminal-report time; this table is for the
``tail -f`` use case — an operator watching a 30-minute test
in real time.

A monotonically-increasing ``seq`` column scoped per ``job_id``
is the cursor: subscribers fetch ``WHERE job_id = X AND seq >
since LIMIT N`` and persist ``next_since`` between polls.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy_utils import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


class LogStream(str, enum.Enum):
    """
        Which channel a chunk belongs to. Operator-meaningful;
        the server doesn't mix-or-merge by stream so the
        consumer can render each colour-coded if it wants.
    """
    STDOUT = "stdout"
    STDERR = "stderr"
    LOG = "log"


class WorkerJobLogChunk(PychestratePhase1Base):
    """
        Append-only log chunk for a worker job.

        :ivar chunk_id: Server-issued primary key.
        :ivar job_id: FK to ``worker_jobs.job_id``.
        :ivar worker_id: FK to ``workers.worker_id``. Nullable so
                         the row survives worker deregistration.
        :ivar attempt: Which attempt of the job produced this
                       chunk, 1-indexed. Lets retried jobs keep
                       prior attempts' output distinguishable.
        :ivar seq: 1-indexed monotonically-increasing sequence
                   per ``job_id``. The cursor for long-poll
                   subscribers.
        :ivar stream: ``stdout`` / ``stderr`` / ``log``.
        :ivar text: The chunk text (UTF-8). Newlines preserved.
        :ivar created_at: Server-side timestamp.
    """

    __tablename__ = "worker_job_log_chunks"
    __table_args__ = (
        Index("ix_worker_job_log_chunks_job_seq", "job_id", "seq"),
        UniqueConstraint(
            "job_id", "seq", name="uq_worker_job_log_chunks_job_seq",
        ),
    )

    chunk_id = Column(UUIDType(binary=False), primary_key=True)
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
    seq = Column(Integer, nullable=False)
    stream = Column(String(16), nullable=False, default=LogStream.STDOUT.value)
    text = Column(Text, nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
