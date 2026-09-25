"""
.. module:: orchestration.rpa.models
    :synopsis: SQLAlchemy models + enums for 6-rpa-orchestration.

.. moduleauthor:: Code Craft AI LLC

Four aggregates make up the RPA domain:

* :class:`RpaJobType` -- a deployment-wide, versioned automation
  identified by a slug. The type declares *how* a job runs
  (``process`` or ``tasker``), the JSON schema its work packet must
  satisfy, the packet paths that carry secrets, and the pod
  capabilities it needs.
* :class:`RpaJobTypeVersion` -- one publishable version of a job
  type: where the code comes from (``source_kind`` / ``source_ref``),
  the entrypoint the client runs, environment, and timeout.
* :class:`RpaSpec` -- a project-scoped binding of a job type to a
  version selector plus default packet fields.
* :class:`RpaJob` -- one triggered execution. ``project_id`` is kept
  as a string reference so the consumer web UI (integer project ids)
  and the orchestration REST surface (UUID project ids) can both own
  RPA specifications; see :func:`orchestration.rpa.packet.
  canonical_project_uuid` for the Layer-5 mapping.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class RpaExecutionMode(str, enum.Enum):
    """
        How a job type runs on the pod client.

        * ``PROCESS`` -- a simple process job: the client hands the
          work packet to a command and the exit code is the result.
        * ``TASKER`` -- a tasker-based job: the client renders the
          work packet into a taskplus workflow and runs the
          ``taskplus`` engine as a subprocess.
    """
    PROCESS = "process"
    TASKER = "tasker"


class RpaJobTypeState(str, enum.Enum):
    """
        Lifecycle of a job type.
    """
    ACTIVE = "active"
    RETIRED = "retired"


class RpaVersionState(str, enum.Enum):
    """
        Lifecycle of a job type version.
    """
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class RpaSourceKind(str, enum.Enum):
    """
        Where a version's code comes from.
    """
    GIT = "git"
    PACKAGE = "package"
    LOCAL = "local"


class RpaJobStatus(str, enum.Enum):
    """
        Lifecycle of one RPA job.
    """
    PENDING = "pending"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


RPA_EXECUTION_MODE_ENUM = "orch_rpa_execution_mode"
RPA_JOB_TYPE_STATE_ENUM = "orch_rpa_job_type_state"
RPA_VERSION_STATE_ENUM = "orch_rpa_version_state"
RPA_SOURCE_KIND_ENUM = "orch_rpa_source_kind"
RPA_JOB_STATUS_ENUM = "orch_rpa_job_status"

#: Selector value meaning "the highest active version at trigger time".
VERSION_SELECTOR_LATEST_ACTIVE: str = "latest-active"


class RpaJobType(PychestratePhase1Base, SerializableModel):
    """
        One registered, deployment-wide RPA job type.
    """

    __tablename__ = "orch_rpa_job_type"

    type_id = Column(String(64), primary_key=True)
    display_name = Column(String(256), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    execution_mode = Column(
        Enum(RpaExecutionMode, name=RPA_EXECUTION_MODE_ENUM),
        nullable=False,
        default=RpaExecutionMode.PROCESS,
    )
    capability_requirements = Column(JSON, nullable=False, default=list)
    packet_schema = Column(JSON, nullable=True)
    secret_fields = Column(JSON, nullable=False, default=list)
    state = Column(
        Enum(RpaJobTypeState, name=RPA_JOB_TYPE_STATE_ENUM),
        nullable=False,
        default=RpaJobTypeState.ACTIVE,
    )
    created_by_id = Column(String(64), nullable=True)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_orch_rpa_job_type_state", "state"),
    )


class RpaJobTypeVersion(PychestratePhase1Base, SerializableModel):
    """
        One published version of a job type.
    """

    __tablename__ = "orch_rpa_job_type_version"

    version_id = Column(UUIDType(binary=False), primary_key=True)
    type_id = Column(
        String(64),
        ForeignKey("orch_rpa_job_type.type_id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(String(64), nullable=False)
    source_kind = Column(
        Enum(RpaSourceKind, name=RPA_SOURCE_KIND_ENUM),
        nullable=False,
        default=RpaSourceKind.GIT,
    )
    source_ref = Column(Text, nullable=False, default="")
    entrypoint = Column(JSON, nullable=False, default=dict)
    environment = Column(JSON, nullable=False, default=dict)
    timeout_minutes = Column(Integer, nullable=False, default=60)
    state = Column(
        Enum(RpaVersionState, name=RPA_VERSION_STATE_ENUM),
        nullable=False,
        default=RpaVersionState.ACTIVE,
    )
    published_by_id = Column(String(64), nullable=True)
    published_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("type_id", "version", name="uq_orch_rpa_type_version"),
        Index("ix_orch_rpa_job_type_version_type_state", "type_id", "state"),
    )


class RpaSpec(PychestratePhase1Base, SerializableModel):
    """
        Project-scoped binding of a job type to a version selector
        and default packet fields.
    """

    __tablename__ = "orch_rpa_spec"

    spec_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    type_id = Column(
        String(64),
        ForeignKey("orch_rpa_job_type.type_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_selector = Column(
        String(64), nullable=False, default=VERSION_SELECTOR_LATEST_ACTIVE,
    )
    default_packet = Column(JSON, nullable=False, default=dict)
    target_pod_id = Column(String(64), nullable=True)
    required_capabilities = Column(JSON, nullable=False, default=list)
    timeout_minutes = Column(Integer, nullable=True)
    description = Column(Text, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    created_by_id = Column(String(64), nullable=True)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_orch_rpa_spec_name"),
        Index("ix_orch_rpa_spec_project", "project_id"),
    )


class RpaSpecRevision(PychestratePhase1Base, SerializableModel):
    """
        Snapshot of a specification as it was at a revision, so a
        job can show the specification it was triggered from.
    """

    __tablename__ = "orch_rpa_spec_revision"

    revision_id = Column(UUIDType(binary=False), primary_key=True)
    spec_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_rpa_spec.spec_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("spec_id", "revision", name="uq_orch_rpa_spec_revision"),
    )


class RpaJob(PychestratePhase1Base, SerializableModel):
    """
        One triggered RPA job.
    """

    __tablename__ = "orch_rpa_job"

    job_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(String(64), nullable=False)
    spec_id = Column(
        UUIDType(binary=False),
        ForeignKey("orch_rpa_spec.spec_id", ondelete="SET NULL"),
        nullable=True,
    )
    spec_name = Column(String(128), nullable=False, default="")
    spec_revision = Column(Integer, nullable=False, default=1)
    type_id = Column(String(64), nullable=False)
    resolved_version = Column(String(64), nullable=False)
    execution_mode = Column(
        Enum(RpaExecutionMode, name=RPA_EXECUTION_MODE_ENUM),
        nullable=False,
        default=RpaExecutionMode.PROCESS,
    )
    work_packet = Column(JSON, nullable=False, default=dict)
    packet_digest = Column(String(64), nullable=False, default="")
    status = Column(
        Enum(RpaJobStatus, name=RPA_JOB_STATUS_ENUM),
        nullable=False,
        default=RpaJobStatus.PENDING,
    )
    exit_code = Column(Integer, nullable=True)
    dispatch_attempt_id = Column(UUIDType(binary=False), nullable=True)
    envelope_id = Column(UUIDType(binary=False), nullable=True)
    client_id = Column(UUIDType(binary=False), nullable=True)
    pod_id = Column(UUIDType(binary=False), nullable=True)
    triggered_by_id = Column(String(64), nullable=True)
    trigger_cause = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False, default="")
    result_root_key = Column(Text, nullable=True)
    final_state_reason = Column(Text, nullable=False, default="")
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(UtcDateTime(timezone=True), nullable=True)
    completed_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_orch_rpa_job_project_created", "project_id", "created_at"),
        Index("ix_orch_rpa_job_project_status", "project_id", "status"),
        Index("ix_orch_rpa_job_spec", "spec_id"),
        Index("ix_orch_rpa_job_idempotency", "idempotency_key"),
    )
