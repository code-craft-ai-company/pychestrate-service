"""
Create Phase 2 M3 hardening tables.

Revision ID: 012_phase2_m3_hardening
Revises: 011_phase2_notifications_m2
Create Date: 2026-04-20

Creates:

- hardening_idempotency_records  -- 48-hour Idempotency-Key dedup table
- retention_legal_holds          -- legal-hold entries scoped per entity

Additional M3 state (rate-limiter buckets, metrics counters, resolution
caches) is in-process and does not require a table.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012_phase2_m3_hardening"
down_revision = "011_phase2_notifications_m2"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create hardening + retention legal-hold tables.
    """
    op.create_table(
        "hardening_idempotency_records",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.VARCHAR(64), nullable=False),
        sa.Column("idempotency_key", sa.VARCHAR(128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("response_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("scope", "idempotency_key", name="ix_hardening_idempotency_scope_key"),
    )

    op.create_table(
        "retention_legal_holds",
        sa.Column("hold_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_kind", sa.VARCHAR(64), nullable=False),
        sa.Column("entity_id", sa.VARCHAR(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("hold_id"),
        sa.UniqueConstraint("entity_kind", "entity_id", name="uq_retention_legal_hold_entity"),
    )
    op.create_index("ix_retention_legal_hold_entity", "retention_legal_holds", ["entity_kind", "entity_id"])

    return


def downgrade():
    """
        Drop M3 hardening tables.
    """
    op.drop_index("ix_retention_legal_hold_entity", table_name="retention_legal_holds")
    op.drop_table("retention_legal_holds")
    op.drop_table("hardening_idempotency_records")
    return
