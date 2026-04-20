"""
Create Phase 2 client-plane tables (client registry + enrollment M1).

Revision ID: 005_phase2_clients
Revises: 004_phase1_identity
Create Date: 2026-04-19

Creates:

- clients_clients                     -- registry row per enrolled client
- clients_client_attributes           -- typed attributes per client
- clients_enrollment_tokens           -- one-shot / multi-use enrollment tokens
- clients_client_revocations          -- rotation / revocation history

The ``clients_client_certs`` table lands in M2 when the mTLS / CSR path
is implemented. M1 tokens redeem to a server-generated bearer token
stored as a digest on ``clients_clients.bearer_token_hash``.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "005_phase2_clients"
down_revision = "004_phase1_identity"
branch_labels = None
depends_on = None


CLIENT_STATUS_ENUM = "clients_client_status"
LIVENESS_STATE_ENUM = "clients_liveness_state"
TOKEN_STATUS_ENUM = "clients_token_status"
REVOCATION_REASON_ENUM = "clients_revocation_reason"


def upgrade():
    """
        Create every Phase 2 M1 table plus the named enum types.
    """
    op.create_table(
        "clients_clients",
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_name", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "SUSPENDED", "REVOKED", name=CLIENT_STATUS_ENUM),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "liveness_state",
            sa.Enum("ALIVE", "DEGRADED", "LOST", name=LIVENESS_STATE_ENUM),
            nullable=False,
            server_default="ALIVE",
        ),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_agent_version", sa.VARCHAR(64), nullable=True),
        sa.Column("transport_name", sa.VARCHAR(64), nullable=True),
        sa.Column("degraded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_token", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column("bearer_token_hash", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("client_id"),
        sa.UniqueConstraint(
            "project_id", "pod_name",
            name="uq_clients_clients_project_pod",
        ),
    )
    op.create_index("ix_clients_clients_liveness", "clients_clients", ["liveness_state"])
    op.create_index("ix_clients_clients_last_seen", "clients_clients", ["last_seen"])
    op.create_index("ix_clients_clients_status", "clients_clients", ["status"])

    op.create_table(
        "clients_client_attributes",
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.VARCHAR(128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["client_id"], ["clients_clients.client_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attribute_id"),
        sa.UniqueConstraint(
            "client_id", "kind",
            name="uq_clients_client_attributes_client_kind",
        ),
    )

    op.create_table(
        "clients_enrollment_tokens",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_name", sa.VARCHAR(128), nullable=False),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("one_shot", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "status",
            sa.Enum("PENDING", "REDEEMED", "EXPIRED", "REVOKED", name=TOKEN_STATUS_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issuer_algorithm", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("token_id"),
    )
    op.create_index(
        "ix_clients_enrollment_tokens_project_status",
        "clients_enrollment_tokens",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_clients_enrollment_tokens_expires",
        "clients_enrollment_tokens",
        ["expires_at"],
    )

    op.create_table(
        "clients_client_revocations",
        sa.Column("revocation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "ROTATED", "DECOMMISSIONED", "COMPROMISED", "ADMIN_REQUEST",
                name=REVOCATION_REASON_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["client_id"], ["clients_clients.client_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revocation_id"),
    )
    return


def downgrade():
    """
        Drop every Phase 2 M1 table + named enum type.
    """
    op.drop_table("clients_client_revocations")
    op.drop_index("ix_clients_enrollment_tokens_expires", table_name="clients_enrollment_tokens")
    op.drop_index("ix_clients_enrollment_tokens_project_status", table_name="clients_enrollment_tokens")
    op.drop_table("clients_enrollment_tokens")
    op.drop_table("clients_client_attributes")
    op.drop_index("ix_clients_clients_status", table_name="clients_clients")
    op.drop_index("ix_clients_clients_last_seen", table_name="clients_clients")
    op.drop_index("ix_clients_clients_liveness", table_name="clients_clients")
    op.drop_table("clients_clients")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name != "postgresql":
        return
    enum_names = [
        REVOCATION_REASON_ENUM,
        TOKEN_STATUS_ENUM,
        LIVENESS_STATE_ENUM,
        CLIENT_STATUS_ENUM,
    ]
    for name in enum_names:
        sa.Enum(name=name).drop(bind, checkfirst=True)
    return
