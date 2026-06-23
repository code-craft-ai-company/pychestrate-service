"""
.. module:: clients.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the client plane.

.. moduleauthor:: Code Craft AI LLC

M1 scope:

- ``clients_clients`` — authoritative client row (project_id, pod_name,
  status, liveness, heartbeat bookkeeping).
- ``clients_client_attributes`` — typed attribute rows contributed by
  ``ClientAttributeExtension`` kinds.
- ``clients_enrollment_tokens`` — one-shot or multi-use enrollment
  tokens. M1 redemption returns a bearer token the agent carries on
  subsequent requests.

M2 additions:

- ``clients_client_certs`` — per-client X.509 certs the service issues
  against its internal CA. ``cert_serial`` is the stable identity the
  pod presents on subsequent traffic. One client MAY accumulate several
  historical cert rows (rotation); ``is_cert_revoked`` walks revocation
  rows by serial so history is preserved.
- ``clients_client_revocations.cert_serial`` — records which serial was
  revoked so the revocation check is a constant-time lookup rather than
  a join through the latest-cert-per-client query.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
    TokenStatus,
)
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


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

        ``cert_serial`` identifies the exact cert that was revoked. A
        client that rotates its cert (new serial) after a revocation
        stays distinct from the revoked serial — the revoked serial
        cannot be re-presented even if a later cert is active.
    """

    __tablename__ = "clients_client_revocations"

    revocation_id = Column(UUIDType(binary=False), primary_key=True)
    client_id = Column(
        UUIDType(binary=False),
        ForeignKey("clients_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    cert_serial = Column(String(64), nullable=True)
    reason = Column(
        Enum(RevocationReason, name="clients_revocation_reason"),
        nullable=False,
    )
    revoked_by = Column(UUIDType(binary=False), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    note = Column(String(512), nullable=False, default="")

    __table_args__ = (
        Index("ix_clients_client_revocations_cert_serial", "cert_serial"),
    )


class ClientCert(PychestratePhase1Base, SerializableModel):
    """
        Per-client X.509 certificate issued against the Pychestrate
        internal CA. ``cert_serial`` is the stable identity the pod
        presents on subsequent traffic; each row captures one issuance
        event, so a rotating client accumulates history rows rather
        than overwriting its current identity.

        ``pem_public`` stores the PEM-encoded signed certificate for
        diagnostics / export; the private key never lands here — it is
        generated on the client side and never leaves its pod.
    """

    __tablename__ = "clients_client_certs"

    cert_serial = Column(String(64), primary_key=True)
    client_id = Column(
        UUIDType(binary=False),
        ForeignKey("clients_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    not_before = Column(DateTime(timezone=True), nullable=False)
    not_after = Column(DateTime(timezone=True), nullable=False)
    issuer_subject = Column(String(256), nullable=False, default="")
    subject_cn = Column(String(128), nullable=False, default="")
    pem_public = Column(Text, nullable=False, default="")
    issued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_clients_client_certs_client_id", "client_id"),
        Index("ix_clients_client_certs_not_after", "not_after"),
    )
