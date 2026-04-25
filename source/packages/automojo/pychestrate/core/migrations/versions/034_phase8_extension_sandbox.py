"""
Add Phase-8 / E-extension-sandbox M1 table.

Revision ID: 034_phase8_extension_sandbox
Revises: 033_phase7_drift_guards
Create Date: 2026-04-25

Adds:

- ``extensions_capability_grant`` (composite PK on
  ``(ext_name, capability)``).
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "034_phase8_extension_sandbox"
down_revision = "033_phase7_drift_guards"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the capability-grant ledger table.
    """
    op.create_table(
        "extensions_capability_grant",
        sa.Column("ext_name", sa.VARCHAR(128), nullable=False),
        sa.Column("capability", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "source",
            sa.VARCHAR(16),
            nullable=False,
            server_default="manifest",
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "ext_name", "capability",
            name="pk_extensions_capability_grant",
        ),
    )
    op.create_index(
        "ix_extensions_capability_grant_ext_revoked",
        "extensions_capability_grant",
        ["ext_name", "revoked_at"],
    )
    return


def downgrade():
    """
        Drop the capability-grant ledger.
    """
    op.drop_index(
        "ix_extensions_capability_grant_ext_revoked",
        table_name="extensions_capability_grant",
    )
    op.drop_table("extensions_capability_grant")
    return
