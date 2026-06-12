"""
Create Phase 2 retention-policies tables (2-retention-policies M1).

Revision ID: 010_phase2_retention
Revises: 009_phase2_notifications
Create Date: 2026-04-20
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010_phase2_retention"
down_revision = "009_phase2_notifications"
branch_labels = None
depends_on = None


POLICY_SCOPE_ENUM = "retention_policy_scope_level"
POLICY_STATE_ENUM = "retention_policy_state"
ACTION_OUTCOME_ENUM = "retention_action_outcome"


def upgrade():
    """
        Create the 2-retention-policies M1 tables.
    """
    op.create_table(
        "retention_policies",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("data_class", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "scope_level",
            sa.Enum("SYSTEM", "PROJECT", name=POLICY_SCOPE_ENUM),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("selector", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("action_chain", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "state",
            sa.Enum("DRAFT", "PUBLISHED", "PAUSED", "ARCHIVED", name=POLICY_STATE_ENUM),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("policy_id"),
        sa.UniqueConstraint(
            "scope_level", "project_id", "name",
            name="uq_retention_policy_name",
        ),
    )
    op.create_index("ix_retention_policy_state", "retention_policies", ["state"])
    op.create_index("ix_retention_policy_data_class", "retention_policies", ["data_class"])

    op.create_table(
        "retention_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retention_policies.policy_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actioned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_retention_runs_policy", "retention_runs", ["policy_id"])

    op.create_table(
        "retention_action_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retention_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.VARCHAR(128), nullable=False),
        sa.Column("action_name", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("APPLIED", "SKIPPED", "FAILED", name=ACTION_OUTCOME_ENUM),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("terminal", sa.VARCHAR(8), nullable=False, server_default="false"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("result_id"),
    )
    op.create_index("ix_retention_action_results_run", "retention_action_results", ["run_id"])

    return


def downgrade():
    """
        Drop the 2-retention-policies M1 tables.
    """
    op.drop_index("ix_retention_action_results_run", table_name="retention_action_results")
    op.drop_table("retention_action_results")

    op.drop_index("ix_retention_runs_policy", table_name="retention_runs")
    op.drop_table("retention_runs")

    op.drop_index("ix_retention_policy_data_class", table_name="retention_policies")
    op.drop_index("ix_retention_policy_state", table_name="retention_policies")
    op.drop_table("retention_policies")

    bind = op.get_bind()
    sa.Enum(name=ACTION_OUTCOME_ENUM).drop(bind, checkfirst=True)
    sa.Enum(name=POLICY_STATE_ENUM).drop(bind, checkfirst=True)
    sa.Enum(name=POLICY_SCOPE_ENUM).drop(bind, checkfirst=True)

    return
