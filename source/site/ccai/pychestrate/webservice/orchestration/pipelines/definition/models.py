"""
.. module:: orchestration.pipelines.definition.models
    :synopsis: SQLAlchemy models + enums for pipeline runs.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class PipelineRunState(str, enum.Enum):
    """
        Lifecycle of a pipeline run.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class StageState(str, enum.Enum):
    """
        Lifecycle of a single pipeline stage.
    """
    PENDING = "pending"
    RUNNING = "running"
    SKIPPED = "skipped"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepState(str, enum.Enum):
    """
        Lifecycle of a single pipeline step.
    """
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TriggerCause(str, enum.Enum):
    """
        How a pipeline run was started.
    """
    MANUAL = "manual"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    API = "api"


PIPELINE_RUN_STATE_ENUM = "orch_pipeline_run_state"
PIPELINE_STAGE_STATE_ENUM = "orch_pipeline_stage_state"
PIPELINE_STEP_STATE_ENUM = "orch_pipeline_step_state"
PIPELINE_TRIGGER_CAUSE_ENUM = "orch_pipeline_trigger_cause"


class PipelineRun(PychestratePhase1Base, SerializableModel):
    """
        One execution of a pipeline document at a specific
        commit. ``pipeline_digest_sha256`` is recorded so two
        runs of the same content can be deduped or compared
        cheaply.
    """

    __tablename__ = "orch_pipeline_run"

    run_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    commit_sha = Column(String(64), nullable=False, default="")
    ref = Column(String(256), nullable=False, default="")
    filename = Column(String(256), nullable=False, default="")
    pipeline_digest_sha256 = Column(String(64), nullable=False, default="")
    state = Column(
        Enum(PipelineRunState, name=PIPELINE_RUN_STATE_ENUM),
        nullable=False,
        default=PipelineRunState.PENDING,
    )
    trigger_cause = Column(
        Enum(TriggerCause, name=PIPELINE_TRIGGER_CAUSE_ENUM),
        nullable=False,
        default=TriggerCause.MANUAL,
    )
    actor_id = Column(UUIDType(binary=False), nullable=True)
    # True when the run is driven by the PipelineOrchestrator (the
    # DAG-walking stage-job dispatch added by 6-pipeline-execution
    # PR p20q). False on M1 definition-only ``trigger_run`` rows that
    # persist stages/steps but never dispatch a Layer-5 job.
    orchestrated = Column(Boolean, nullable=False, default=False)
    started_at = Column(UtcDateTime(timezone=True), nullable=True)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_orch_pipeline_run_project_state", "project_id", "state"),
        Index("ix_orch_pipeline_run_commit_filename", "commit_sha", "filename"),
        Index("ix_orch_pipeline_run_digest", "pipeline_digest_sha256"),
    )


class PipelineStageRun(PychestratePhase1Base, SerializableModel):
    """
        Per-stage record. ``stage_id`` is the document-declared
        identifier; ``stage_index`` preserves the original
        document ordering.
    """

    __tablename__ = "orch_pipeline_stage_run"

    stage_run_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_pipeline_run.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id = Column(String(128), nullable=False)
    stage_index = Column(Integer, nullable=False, default=0)
    state = Column(
        Enum(StageState, name=PIPELINE_STAGE_STATE_ENUM),
        nullable=False,
        default=StageState.PENDING,
    )
    when_clause = Column(String(64), nullable=False, default="succeeded")
    when_clause_resolved = Column(String(64), nullable=False, default="")
    needs_csv = Column(Text, nullable=False, default="")
    started_at = Column(UtcDateTime(timezone=True), nullable=True)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_orch_pipeline_stage_run_run", "run_id"),
        Index(
            "ix_orch_pipeline_stage_run_run_index",
            "run_id", "stage_index",
        ),
    )


class PipelineStepRun(PychestratePhase1Base, SerializableModel):
    """
        Per-step record. ``layer5_run_id`` is bound by Layer-5
        once the step dispatches; ``kind_name`` is the registered
        :class:`PipelineStepKindProtocol` name.
    """

    __tablename__ = "orch_pipeline_step_run"

    step_run_id = Column(UUIDType(binary=False), primary_key=True)
    stage_run_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_pipeline_stage_run.stage_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id = Column(String(128), nullable=False)
    step_index = Column(Integer, nullable=False, default=0)
    kind_name = Column(String(64), nullable=False, default="")
    job_kind = Column(String(32), nullable=False, default="")
    layer5_run_id = Column(UUIDType(binary=False), nullable=True)
    state = Column(
        Enum(StepState, name=PIPELINE_STEP_STATE_ENUM),
        nullable=False,
        default=StepState.PENDING,
    )
    attempt = Column(Integer, nullable=False, default=0)
    inputs = Column(JSON, nullable=False, default=dict)
    started_at = Column(UtcDateTime(timezone=True), nullable=True)
    finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_orch_pipeline_step_run_stage", "stage_run_id"),
        Index("ix_orch_pipeline_step_run_layer5", "layer5_run_id"),
    )


class PipelineDocumentCache(PychestratePhase1Base, SerializableModel):
    """
        Cache of canonicalized pipeline documents keyed by
        ``(project_id, commit_sha, filename)``. M1 stores the
        canonical JSON inline; M2 moves it to the object store
        and replaces ``canonical_json`` with a blob key.
    """

    __tablename__ = "orch_pipeline_document_cache"

    project_id = Column(UUIDType(binary=False), nullable=False)
    commit_sha = Column(String(64), nullable=False)
    filename = Column(String(256), nullable=False)
    pipeline_digest_sha256 = Column(String(64), nullable=False)
    canonical_json = Column(Text, nullable=False, default="")
    cached_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "commit_sha", "filename",
            name="pk_orch_pipeline_document_cache",
        ),
        Index(
            "ix_orch_pipeline_document_cache_digest",
            "pipeline_digest_sha256",
        ),
    )
