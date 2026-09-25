"""
.. module:: pods.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for every Layer-3 pod feature.

.. moduleauthor:: Code Craft AI LLC

Because the six Layer-3 pod specs are tightly coupled (definitions feed
registrations, registrations drive lifecycle, lifecycle triggers
scoped-config purges, dynamic provisioning materializes into the same
definitions), their tables live in a single module so foreign keys
resolve during ``create_all``.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


_Json = JSON().with_variant(JSONB(), "postgresql")


class PodState(enum.Enum):
    """
        3-pod-lifecycle canonical states.
    """
    DEFINED = "DEFINED"
    PROVISIONING = "PROVISIONING"
    READY = "READY"
    IN_USE = "IN_USE"
    DRAINING = "DRAINING"
    RELEASED = "RELEASED"
    CLIENT_LOST = "CLIENT_LOST"
    FAILED = "FAILED"


class RegistrationState(enum.Enum):
    """
        3-static-pods registration state.
    """
    REGISTERED = "REGISTERED"
    CLIENT_LOST = "CLIENT_LOST"
    DRAINING = "DRAINING"
    DEREGISTERED = "DEREGISTERED"


class MaterializationState(enum.Enum):
    """
        3-dynamic-pods materialization state.
    """
    PENDING = "PENDING"
    RENDERING = "RENDERING"
    RESERVING = "RESERVING"
    PROVISIONING = "PROVISIONING"
    AWAITING_CLIENT = "AWAITING_CLIENT"
    READY = "READY"
    FAILED = "FAILED"
    RELEASED = "RELEASED"


class PodDefinition(PychestratePhase1Base, SerializableModel):
    """
        Canonical pod record (3-pod-definitions).
    """
    __tablename__ = "pods_definitions"

    pod_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    pod_name = Column(String(128), nullable=False)
    current_version = Column(Integer(), nullable=False, default=1)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)
    deleted_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "pod_name", name="uq_pods_definition_project_name"),
        Index("ix_pods_definition_project", "project_id"),
    )


class PodDefinitionVersion(PychestratePhase1Base, SerializableModel):
    """
        Immutable versioned spec body for a :class:`PodDefinition`.
    """
    __tablename__ = "pods_definition_versions"

    pod_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"),
        primary_key=True,
    )
    version = Column(Integer(), primary_key=True)
    spec_json = Column(_Json, nullable=False, default=dict)
    spec_hash = Column(String(64), nullable=False)
    validator_report = Column(_Json, nullable=False, default=dict)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)


class PodRuntimeState(PychestratePhase1Base, SerializableModel):
    """
        3-pod-lifecycle current-state row.
    """
    __tablename__ = "pods_runtime_state"

    pod_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state = Column(
        Enum(PodState, name="pods_pod_state"),
        nullable=False,
        default=PodState.DEFINED,
    )
    previous_state = Column(
        Enum(PodState, name="pods_pod_state"),
        nullable=True,
    )
    last_transition_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    last_transition_event = Column(String(64), nullable=True)
    in_use_since = Column(UtcDateTime(timezone=True), nullable=True)
    runs_remaining = Column(Integer(), nullable=True)
    transition_cursor = Column(Integer(), nullable=False, default=0)


class PodLifecycleLog(PychestratePhase1Base, SerializableModel):
    """
        Append-only lifecycle transition log.
    """
    __tablename__ = "pods_lifecycle_log"

    log_id = Column(UUIDType(binary=False), primary_key=True)
    pod_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_state = Column(Enum(PodState, name="pods_pod_state"), nullable=True)
    to_state = Column(Enum(PodState, name="pods_pod_state"), nullable=False)
    event_kind = Column(String(64), nullable=False)
    event_payload = Column(_Json, nullable=False, default=dict)
    actor = Column(String(128), nullable=True)
    applied_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_pods_lifecycle_log_pod", "pod_id"),
    )


class PodRegistration(PychestratePhase1Base, SerializableModel):
    """
        3-static-pods registration row.
    """
    __tablename__ = "pods_registrations"

    registration_id = Column(UUIDType(binary=False), primary_key=True)
    pod_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"),
        nullable=False,
    )
    pod_definition_version = Column(Integer(), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=True)
    state = Column(
        Enum(RegistrationState, name="pods_registration_state"),
        nullable=False,
        default=RegistrationState.REGISTERED,
    )
    report_hash = Column(String(64), nullable=False)
    report_json = Column(_Json, nullable=False, default=dict)
    registered_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    last_report_at = Column(UtcDateTime(timezone=True), nullable=True)
    deregistered_at = Column(UtcDateTime(timezone=True), nullable=True)
    deregister_reason = Column(String(256), nullable=True)
    client_lost_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_pods_registration_pod", "pod_id"),
        Index("ix_pods_registration_state", "state"),
    )


class PodTemplate(PychestratePhase1Base, SerializableModel):
    """
        3-dynamic-pods template record.
    """
    __tablename__ = "pods_templates"

    template_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    template_kind = Column(String(64), nullable=False)
    source_version = Column(Integer(), nullable=False, default=1)
    source_json = Column(_Json, nullable=False, default=dict)
    parameter_schema = Column(_Json, nullable=False, default=dict)
    created_by = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_pods_template_project_name"),
    )


class DynamicPodMaterialization(PychestratePhase1Base, SerializableModel):
    """
        A single materialization attempt for a :class:`PodTemplate`.
    """
    __tablename__ = "pods_dynamic_materializations"

    materialization_id = Column(UUIDType(binary=False), primary_key=True)
    template_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_templates.template_id", ondelete="CASCADE"),
        nullable=False,
    )
    template_source_version = Column(Integer(), nullable=False)
    parameters_json = Column(_Json, nullable=False, default=dict)
    rendered_spec_json = Column(_Json, nullable=False, default=dict)
    pod_id = Column(
        UUIDType(binary=False),
        ForeignKey("pods_definitions.pod_id", ondelete="SET NULL"),
        nullable=True,
    )
    state = Column(
        Enum(MaterializationState, name="pods_materialization_state"),
        nullable=False,
        default=MaterializationState.PENDING,
    )
    current_step = Column(String(64), nullable=True)
    error_summary = Column(Text(), nullable=True)
    reservation_ids = Column(_Json, nullable=False, default=list)
    requested_by = Column(UUIDType(binary=False), nullable=True)
    requested_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    ready_at = Column(UtcDateTime(timezone=True), nullable=True)
    orphaned_reason = Column(String(256), nullable=True)


class PodScopedBearer(PychestratePhase1Base, SerializableModel):
    """
        3-pod-scoped-config ephemeral bearer reference (M2).
    """
    __tablename__ = "pods_scoped_bearers"

    bearer_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    pod_id = Column(UUIDType(binary=False), nullable=False)
    secret_ref = Column(String(512), nullable=False)
    policy = Column(_Json, nullable=False, default=dict)
    issued_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(UtcDateTime(timezone=True), nullable=True)
    consumed = Column(Boolean(), nullable=False, default=False)

    __table_args__ = (
        Index("ix_pods_scoped_bearer_run", "run_id"),
    )


class PodRunVariable(PychestratePhase1Base, SerializableModel):
    """
        3-pod-scoped-config per-run variable binding.
    """
    __tablename__ = "pods_run_variables"

    variable_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    pod_id = Column(UUIDType(binary=False), nullable=False)
    name = Column(String(128), nullable=False)
    value_json = Column(_Json, nullable=False, default=dict)
    value_schema = Column(_Json, nullable=True)
    locked = Column(Boolean(), nullable=False, default=False)
    set_by = Column(UUIDType(binary=False), nullable=True)
    set_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("run_id", "pod_id", "name", name="uq_pods_run_variable_scope"),
        Index("ix_pods_run_variable_run", "run_id"),
    )
