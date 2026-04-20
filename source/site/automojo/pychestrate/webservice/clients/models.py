"""
.. module:: clients.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the client plane.

.. moduleauthor:: Automation Mojo LLC

M1 scope:

- ``clients_clients`` — authoritative client row (project_id, pod_name,
  status, liveness, heartbeat bookkeeping).
- ``clients_client_attributes`` — typed attribute rows contributed by
  ``ClientAttributeExtension`` kinds.
- ``clients_enrollment_tokens`` — one-shot or multi-use enrollment
  tokens. M1 redemption returns a bearer token the agent carries on
  subsequent requests; the full mTLS / CSR path lands in M2 via a
  separate ``clients_client_certs`` table.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
    TokenStatus,
)
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class Client(PychestratePhase1Base, SerializableModel):
    """
        Authoritative client record. ``(project_id, pod_name)`` is unique
        so re-enrollment under the same scope collides until the existing
        client is revoked.
    """

    __tablename__ = "clients_clients"

    client_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    pod_name = Column(String(128), nullable=False)
    status = Column(
        Enum(ClientStatus, name="clients_client_status"),
        nullable=False,
        default=ClientStatus.ACTIVE,
    )
    liveness_state = Column(
        Enum(LivenessState, name="clients_liveness_state"),
        nullable=False,
        default=LivenessState.ALIVE,
    )
    enrolled_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    last_agent_version = Column(String(64), nullable=True)
    transport_name = Column(String(64), nullable=True)
    degraded_at = Column(DateTime(timezone=True), nullable=True)
    revision_token = Column(String(128), nullable=False, default="")
    bearer_token_hash = Column(LargeBinary, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "pod_name",
            name="uq_clients_clients_project_pod",
        ),
        Index("ix_clients_clients_liveness", "liveness_state"),
        Index("ix_clients_clients_last_seen", "last_seen"),
        Index("ix_clients_clients_status", "status"),
    )


class ClientAttribute(PychestratePhase1Base, SerializableModel):
    """
        Per-client typed attribute row. One row per declared
        ``ClientAttributeExtension`` kind.
    """

    __tablename__ = "clients_client_attributes"

    attribute_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(
        UUIDType(binary=False),
        ForeignKey("clients_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(128), nullable=False)
    value_json = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "client_id", "kind",
            name="uq_clients_client_attributes_client_kind",
        ),
    )


class EnrollmentToken(PychestratePhase1Base, SerializableModel):
    """
        Enrollment token row. ``token_hash`` is the server-side digest of
        the secret returned exactly once at issuance. The secret itself is
        never persisted.
    """

    __tablename__ = "clients_enrollment_tokens"

    token_id = Column(UUIDType(binary=False), primary_key=True)
    token_hash = Column(LargeBinary, nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    pod_name = Column(String(128), nullable=False)
    issued_by = Column(UUIDType(binary=False), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    one_shot = Column(Boolean, nullable=False, default=True)
    status = Column(
        Enum(TokenStatus, name="clients_token_status"),
        nullable=False,
        default=TokenStatus.PENDING,
    )
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    redeemed_by_client_id = Column(UUIDType(binary=False), nullable=True)
    issuer_algorithm = Column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_clients_enrollment_tokens_project_status", "project_id", "status"),
        Index("ix_clients_enrollment_tokens_expires", "expires_at"),
    )


class ClientRevocation(PychestratePhase1Base, SerializableModel):
    """
        Revocation history. One row per revoke call. Kept separate from
        the client row so multi-rotation history is preserved.
    """

    __tablename__ = "clients_client_revocations"

    revocation_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(
        UUIDType(binary=False),
        ForeignKey("clients_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    reason = Column(
        Enum(RevocationReason, name="clients_revocation_reason"),
        nullable=False,
    )
    revoked_by = Column(UUIDType(binary=False), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    note = Column(String(512), nullable=False, default="")
