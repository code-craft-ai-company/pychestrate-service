"""
.. module:: secrets.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-secrets-vault feature.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
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
    LargeBinary,
    String,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class SecretVersionState(enum.Enum):
    """
        Lifecycle state for one version of a secret.
    """
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class SecretOutboxStatus(enum.Enum):
    """
        Lifecycle state for an entry in the secrets async outbox.
    """
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class SecretRecord(PychestratePhase1Base, SerializableModel):
    """
        Metadata per secret_ref.

        Physical table name is ``phase1_secrets`` during the parallel-run
        with the legacy ``secrets`` table. The Phase 10 cut-over renames
        this to ``secrets`` once the legacy table is retired.
    """

    __tablename__ = "phase1_secrets"

    secret_ref = Column(String(256), primary_key=True)
    current_version_id = Column(UUIDType(binary=False), nullable=True)
    backend_name = Column(String(128), nullable=False)
    owner_user_id = Column(UUIDType(binary=False), nullable=True)
    owner_project_id = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class SecretVersion(PychestratePhase1Base, SerializableModel):
    """
        Rotation lineage row per secret version.

        Physical table name is ``phase1_secret_versions`` during parallel-run.
    """

    __tablename__ = "phase1_secret_versions"

    version_id = Column(UUIDType(binary=False), primary_key=True)
    secret_ref = Column(
        String(256),
        ForeignKey("phase1_secrets.secret_ref", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    state = Column(Enum(SecretVersionState, name="secret_version_state"), nullable=False)
    ciphertext_ref = Column(String(256), nullable=True)
    ciphertext_bytes = Column(LargeBinary, nullable=True)
    wrapped_dek = Column(LargeBinary, nullable=True)
    kek_id = Column(String(128), nullable=True)
    grace_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)

    __table_args__ = (
        Index("ix_secret_versions_ref_number", "secret_ref", "version_number", unique=True),
    )


class SecretAcl(PychestratePhase1Base, SerializableModel):
    """
        Per-secret ACL rule.
    """

    __tablename__ = "secret_acls"

    acl_id = Column(UUIDType(binary=False), primary_key=True)
    secret_ref = Column(
        String(256),
        ForeignKey("phase1_secrets.secret_ref", ondelete="CASCADE"),
        nullable=False,
    )
    effect = Column(String(16), nullable=False)
    principal_kind = Column(String(16), nullable=False)
    principal_id = Column(UUIDType(binary=False), nullable=False)
    actions_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)


class SecretOutboxEntry(PychestratePhase1Base, SerializableModel):
    """
        Async outbox buffer for non-sync writes.
    """

    __tablename__ = "secret_outbox"

    outbox_id = Column(UUIDType(binary=False), primary_key=True)
    operation = Column(String(64), nullable=False)
    payload = Column(LargeBinary, nullable=False)
    enqueued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    retry_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(SecretOutboxStatus, name="secret_outbox_status"), nullable=False)
