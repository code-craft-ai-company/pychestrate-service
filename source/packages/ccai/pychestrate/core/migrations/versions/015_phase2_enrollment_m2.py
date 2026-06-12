"""
Add Phase 2 M2 client-enrollment cert tables.

Revision ID: 015_phase2_enrollment_m2
Revises: 014_phase3_layer3_m2
Create Date: 2026-04-24

Adds:

- ``clients_client_certs`` — per-client X.509 certificates issued
  against the Pychestrate internal CA. ``cert_serial`` is the stable
  identity presented on subsequent pod traffic. One row per issuance;
  rotation accumulates history rather than overwriting.
- ``clients_client_revocations.cert_serial`` — column + index so the
  revocation check is a constant-time lookup by serial.

This migration is the first M2 deliverable for ``3-client-enrollment``
(mTLS / CSR / CA path). M1 persisted only bearer-token hashes on the
client row; M2 introduces the cert identity alongside the bearer.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "015_phase2_enrollment_m2"
down_revision = "014_phase3_layer3_m2"
branch_labels = None
depends_on = None


CLIENT_REVOCATION_CERT_INDEX = "ix_clients_client_revocations_cert_serial"
CLIENT_CERTS_CLIENT_INDEX = "ix_clients_client_certs_client_id"
CLIENT_CERTS_NOT_AFTER_INDEX = "ix_clients_client_certs_not_after"


def upgrade():
    """
        Create ``clients_client_certs`` and add ``cert_serial`` to
        ``clients_client_revocations`` with a supporting index.
    """
    op.create_table(
        "clients_client_certs",
        sa.Column("cert_serial", sa.VARCHAR(64), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issuer_subject", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("subject_cn", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column("pem_public", sa.Text(), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("cert_serial"),
        sa.ForeignKeyConstraint(
            ["client_id"], ["clients_clients.client_id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        CLIENT_CERTS_CLIENT_INDEX,
        "clients_client_certs",
        ["client_id"],
    )
    op.create_index(
        CLIENT_CERTS_NOT_AFTER_INDEX,
        "clients_client_certs",
        ["not_after"],
    )

    op.add_column(
        "clients_client_revocations",
        sa.Column("cert_serial", sa.VARCHAR(64), nullable=True),
    )
    op.create_index(
        CLIENT_REVOCATION_CERT_INDEX,
        "clients_client_revocations",
        ["cert_serial"],
    )

    return


def downgrade():
    """
        Drop the M2-only columns + table. The underlying revocation
        table and the client row are left in place because they
        predate this migration.
    """
    op.drop_index(
        CLIENT_REVOCATION_CERT_INDEX,
        table_name="clients_client_revocations",
    )
    op.drop_column("clients_client_revocations", "cert_serial")

    op.drop_index(CLIENT_CERTS_NOT_AFTER_INDEX, table_name="clients_client_certs")
    op.drop_index(CLIENT_CERTS_CLIENT_INDEX, table_name="clients_client_certs")
    op.drop_table("clients_client_certs")

    return
