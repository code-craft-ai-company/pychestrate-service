"""
.. module:: ingest.progress.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the progress receiver.

.. moduleauthor:: Automation Mojo LLC

Three tables capture progress observations:

- ``ingest_run_progress_summary`` — one row per posted summary.
- ``ingest_run_progress_record`` — one row per individual test
  record. ``UNIQUE (run_id, record_index)`` so the client
  re-posting the same record is a no-op.
- ``ingest_run_progress_counters`` — one rolling-counter row per
  run; fast path for the live-run-view roll-up.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class RunProgressSummary(PychestratePhase1Base, SerializableModel):
    """
        Snapshot of a forwarded ``ForwardingInfo`` summary.
    """

    __tablename__ = "ingest_run_progress_summary"

    summary_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    format_tag = Column(String(64), nullable=False, default="")
    tests_total = Column(Integer, nullable=True)
    tests_passed = Column(Integer, nullable=False, default=0)
    tests_failed = Column(Integer, nullable=False, default=0)
    tests_skipped = Column(Integer, nullable=False, default=0)
    tests_errored = Column(Integer, nullable=False, default=0)
    percent_complete = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    raw_payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_ingest_run_progress_summary_run_id", "run_id"),
        Index("ix_ingest_run_progress_summary_received_at", "received_at"),
    )


class RunProgressRecord(PychestratePhase1Base, SerializableModel):
    """
        One persisted record from the testbase results stream.
    """

    __tablename__ = "ingest_run_progress_record"

    record_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    record_index = Column(Integer, nullable=False)
    test_name = Column(String(512), nullable=False, default="")
    result = Column(String(32), nullable=False, default="UNSET")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    raw_payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "record_index",
            name="uq_ingest_run_progress_record_run_index",
        ),
        Index("ix_ingest_run_progress_record_run_id", "run_id"),
        Index("ix_ingest_run_progress_record_result", "result"),
    )


class RunProgressCounters(PychestratePhase1Base, SerializableModel):
    """
        Rolling counter row — one per run. Updated whenever a
        summary lands so live-run-view does not have to aggregate.
    """

    __tablename__ = "ingest_run_progress_counters"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    tests_total = Column(Integer, nullable=True)
    tests_passed = Column(Integer, nullable=False, default=0)
    tests_failed = Column(Integer, nullable=False, default=0)
    tests_skipped = Column(Integer, nullable=False, default=0)
    tests_errored = Column(Integer, nullable=False, default=0)
    percent_complete = Column(Float, nullable=True)
    last_summary_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_ingest_run_progress_counters_project_id", "project_id"),
    )
