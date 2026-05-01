"""
.. module:: workers.joblogservice
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-layer operations for live job log chunks.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.joblogmodels import (
    LogStream,
    WorkerJobLogChunk,
)
from automojo.pychestrate.webservice.workers.jobmodels import WorkerJob


@dataclass(frozen=True)
class LogChunkView:
    """
        Caller-facing snapshot of a :class:`WorkerJobLogChunk`.
    """
    chunk_id: str
    job_id: str
    worker_id: Optional[str]
    attempt: int
    seq: int
    stream: str
    text: str
    created_at: str


def _to_view(*, row: WorkerJobLogChunk) -> LogChunkView:
    if row.worker_id is not None:
        worker_field: Optional[str] = str(row.worker_id)
    else:
        worker_field = None
    rtnval = LogChunkView(
        chunk_id=str(row.chunk_id),
        job_id=str(row.job_id),
        worker_id=worker_field,
        attempt=int(row.attempt) if row.attempt is not None else 1,
        seq=int(row.seq),
        stream=row.stream,
        text=row.text if row.text is not None else "",
        created_at=row.created_at.isoformat(),
    )
    return rtnval


def _coerce_stream(*, value) -> str:
    if value is None:
        rtnval = LogStream.STDOUT.value
        return rtnval
    if isinstance(value, LogStream):
        rtnval = value.value
        return rtnval
    raw = str(value).strip()
    try:
        rtnval = LogStream(raw).value
    except ValueError:
        # Operator-defined stream names are accepted as-is for
        # forward compatibility — the column is a String, not
        # an enum constraint.
        rtnval = raw if len(raw) > 0 else LogStream.STDOUT.value
    return rtnval


def _next_seq_for_job(
        *,
        db_session: DbSession,
        job_id: str,
    ) -> int:
    """
        Compute the next sequence number for this job by reading
        the current MAX. Single-writer-per-job is the model
        (only the claiming worker streams), so this is safe
        without a row-level lock; the unique constraint on
        ``(job_id, seq)`` is the belt-and-braces.
    """
    current = (
        db_session.query(sa_func.max(WorkerJobLogChunk.seq))
        .filter(WorkerJobLogChunk.job_id == job_id)
        .scalar()
    )
    if current is None:
        rtnval = 1
        return rtnval
    rtnval = int(current) + 1
    return rtnval


def append_log_chunk(
        *,
        db_session: DbSession,
        job_id: str,
        worker_id: Optional[str],
        text: str,
        stream=None,
    ) -> LogChunkView:
    """
        Append a new chunk to ``job_id``'s log stream.

        :raises LookupError: When ``job_id`` is unknown.
    """
    if text is None:
        text_value = ""
    else:
        text_value = str(text)
    job_row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if job_row is None:
        err_lines = [
            "Worker job not found.",
            "JOB_ID: {}".format(job_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise LookupError(err_msg) from None

    seq = _next_seq_for_job(db_session=db_session, job_id=job_id)
    attempt_value = (
        int(job_row.attempt) if job_row.attempt is not None else 1
    )
    row = WorkerJobLogChunk(
        chunk_id=new_uuid(),
        job_id=job_id,
        worker_id=worker_id,
        attempt=attempt_value,
        seq=seq,
        stream=_coerce_stream(value=stream),
        text=text_value,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def read_log_chunks(
        *,
        db_session: DbSession,
        job_id: str,
        since_seq: int = 0,
        limit: int = 200,
    ) -> List[LogChunkView]:
    """
        Read chunks for ``job_id`` whose ``seq > since_seq``,
        ordered ascending so the consumer can simply append.
        ``limit`` is clamped to ``[1, 1000]`` so a runaway
        long-poll can't OOM the API.
    """
    if limit < 1:
        limit_value = 1
    elif limit > 1000:
        limit_value = 1000
    else:
        limit_value = int(limit)
    if since_seq < 0:
        since_value = 0
    else:
        since_value = int(since_seq)
    rows = (
        db_session.query(WorkerJobLogChunk)
        .filter(WorkerJobLogChunk.job_id == job_id)
        .filter(WorkerJobLogChunk.seq > since_value)
        .order_by(WorkerJobLogChunk.seq.asc())
        .limit(limit_value)
        .all()
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def latest_seq_for_job(
        *,
        db_session: DbSession,
        job_id: str,
    ) -> int:
    """
        Return the max ``seq`` for ``job_id``, or ``0`` when
        there are no chunks. Useful for "start tailing from
        now".
    """
    current = (
        db_session.query(sa_func.max(WorkerJobLogChunk.seq))
        .filter(WorkerJobLogChunk.job_id == job_id)
        .scalar()
    )
    if current is None:
        rtnval = 0
        return rtnval
    rtnval = int(current)
    return rtnval
