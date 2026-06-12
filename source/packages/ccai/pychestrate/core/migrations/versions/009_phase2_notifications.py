"""
Create Phase 2 notification-hub tables (2-notification-hub M1).

Revision ID: 009_phase2_notifications
Revises: 008_phase2_global_variables
Create Date: 2026-04-20
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "009_phase2_notifications"
down_revision = "008_phase2_global_variables"
branch_labels = None
depends_on = None


SCOPE_LEVEL_ENUM = "notifications_scope_level"
DISPATCH_OUTCOME_ENUM = "notifications_dispatch_outcome"


def upgrade():
    """
        Create the 2-notification-hub M1 tables.
    """
    op.create_table(
        "notifications_channels",
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("kind", sa.VARCHAR(32), nullable=False),
        sa.Column(
            "scope_level",
            sa.Enum("SYSTEM", "PROJECT", name=SCOPE_LEVEL_ENUM),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("channel_id"),
        sa.UniqueConstraint(
            "scope_level", "project_id", "name",
            name="uq_notifications_channels_name",
        ),
    )
    op.create_index("ix_notifications_channels_kind", "notifications_channels", ["kind"])

    op.create_table(
        "notifications_routing_rules",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_pattern", sa.VARCHAR(128), nullable=False),
        sa.Column("filter_tag_expression", sa.VARCHAR(512), nullable=True),
        sa.Column("recipients", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("channel_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("template_name", sa.VARCHAR(128), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("rule_id"),
    )
    op.create_index("ix_notifications_routing_project", "notifications_routing_rules", ["project_id"])
    op.create_index("ix_notifications_routing_pattern", "notifications_routing_rules", ["event_pattern"])

    op.create_table(
        "notifications_dispatch_envelopes",
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_topic", sa.VARCHAR(128), nullable=False),
        sa.Column("recipient", sa.VARCHAR(320), nullable=False),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications_channels.channel_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_name", sa.VARCHAR(128), nullable=False),
        sa.Column("severity", sa.VARCHAR(16), nullable=False, server_default="INFO"),
        sa.Column("rendered_subject", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("rendered_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("envelope_id"),
    )
    op.create_index("ix_notifications_dispatch_channel", "notifications_dispatch_envelopes", ["channel_id"])
    op.create_index("ix_notifications_dispatch_topic", "notifications_dispatch_envelopes", ["event_topic"])

    op.create_table(
        "notifications_dispatch_attempts",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "envelope_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "notifications_dispatch_envelopes.envelope_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "outcome",
            sa.Enum("DELIVERED", "FAILED", "DEFERRED", name=DISPATCH_OUTCOME_ENUM),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_notifications_attempts_envelope",
        "notifications_dispatch_attempts",
        ["envelope_id"],
    )

    return


def downgrade():
    """
        Drop the 2-notification-hub M1 tables.
    """
    op.drop_index("ix_notifications_attempts_envelope", table_name="notifications_dispatch_attempts")
    op.drop_table("notifications_dispatch_attempts")

    op.drop_index("ix_notifications_dispatch_topic", table_name="notifications_dispatch_envelopes")
    op.drop_index("ix_notifications_dispatch_channel", table_name="notifications_dispatch_envelopes")
    op.drop_table("notifications_dispatch_envelopes")

    op.drop_index("ix_notifications_routing_pattern", table_name="notifications_routing_rules")
    op.drop_index("ix_notifications_routing_project", table_name="notifications_routing_rules")
    op.drop_table("notifications_routing_rules")

    op.drop_index("ix_notifications_channels_kind", table_name="notifications_channels")
    op.drop_table("notifications_channels")

    bind = op.get_bind()
    sa.Enum(name=DISPATCH_OUTCOME_ENUM).drop(bind, checkfirst=True)
    sa.Enum(name=SCOPE_LEVEL_ENUM).drop(bind, checkfirst=True)

    return
