"""
Add Phase 2 notification-hub M2 tables (preferences + dead-letters).

Revision ID: 011_phase2_notifications_m2
Revises: 010_phase2_retention
Create Date: 2026-04-20
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "011_phase2_notifications_m2"
down_revision = "010_phase2_retention"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the M2 user preferences + dead-letter tables.
    """
    op.create_table(
        "notifications_user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topics_enabled", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("quiet_hours", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "notifications_dead_letters",
        sa.Column(
            "envelope_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "notifications_dispatch_envelopes.envelope_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replayable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("parked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("envelope_id"),
    )
    return


def downgrade():
    """
        Drop the M2 notification-hub tables.
    """
    op.drop_table("notifications_dead_letters")
    op.drop_table("notifications_user_preferences")
    return
