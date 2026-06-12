"""
.. module:: ingest.result.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the result ingester.

.. moduleauthor:: Code Craft AI LLC

Four tables:

- ``ingest_run_result_summary`` — one row per run capturing the
  testbase ``testrun_summary.json`` roll-up.
- ``ingest_task_result`` — one row per individual test scope
  result (the JSOS records).
- ``ingest_run_artifact`` — one row per artifact file the
  watcher catalogued.
- ``ingest_result_scan_attempt`` — one row per scan attempt
  (success or failure) for observability.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ScanOutcomeStatus(str, enum.Enum):
    """
        Lifecycle of one scan attempt.
    """
    SCANNED = "scanned"
    NOT_FOUND = "not_found"
    FAILED = "failed"


SCAN_OUTCOME_STATUS_ENUM = "ingest_scan_outcome_status"


class RunResultSummary(PychestratePhase1Base, SerializableModel):
    """
        Roll-up parsed from ``testrun_summary.json``.
    """

    __tablename__ = "ingest_run_result_summary"

    summary_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    parser_tag = Column(String(64), nullable=False, default="")
    tests_total = Column(Integer, nullable=False, default=0)
    tests_passed = Column(Integer, nullable=False, default=0)
    tests_failed = Column(Integer, nullable=False, default=0)
    tests_skipped = Column(Integer, nullable=False, default=0)
    tests_errored = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    raw_payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_ingest_run_result_summary_run",
        ),
        Index("ix_ingest_run_result_summary_project", "project_id"),
    )


class TaskResult(PychestratePhase1Base, SerializableModel):
    """
        One persisted test-scope result.
    """

    __tablename__ = "ingest_task_result"

    task_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    test_name = Column(String(512), nullable=False, default="")
    instance_uuid = Column(String(64), nullable=False, default="")
    rtype = Column(String(32), nullable=False, default="TEST")
    result = Column(String(32), nullable=False, default="UNSET")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    raw_payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "instance_uuid",
            name="uq_ingest_task_result_run_instance",
        ),
        Index("ix_ingest_task_result_run", "run_id"),
        Index("ix_ingest_task_result_result", "result"),
    )


class RunArtifact(PychestratePhase1Base, SerializableModel):
    """
        One catalogued artifact file from the result tree.
    """

    __tablename__ = "ingest_run_artifact"

    artifact_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    relative_path = Column(String(1024), nullable=False, default="")
    classification = Column(String(64), nullable=False, default="other")
    size_bytes = Column(BigInteger, nullable=False, default=0)
    content_type = Column(String(128), nullable=True)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "relative_path",
            name="uq_ingest_run_artifact_run_path",
        ),
        Index("ix_ingest_run_artifact_run", "run_id"),
        Index("ix_ingest_run_artifact_classification", "classification"),
    )


class ResultScanAttempt(PychestratePhase1Base, SerializableModel):
    """
        Observability row — one per :func:`scan_once` call.
    """

    __tablename__ = "ingest_result_scan_attempt"

    attempt_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        Enum(ScanOutcomeStatus, name=SCAN_OUTCOME_STATUS_ENUM),
        nullable=False,
        default=ScanOutcomeStatus.SCANNED,
    )
    files_seen = Column(Integer, nullable=False, default=0)
    artifacts_persisted = Column(Integer, nullable=False, default=0)
    tasks_persisted = Column(Integer, nullable=False, default=0)
    failure_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ingest_result_scan_attempt_run", "run_id"),
        Index("ix_ingest_result_scan_attempt_status", "status"),
    )
