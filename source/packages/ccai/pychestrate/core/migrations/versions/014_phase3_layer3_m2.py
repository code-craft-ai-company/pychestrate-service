"""
Add Phase 3 Layer-3 M2 tables (rollout stages, pod pins, scoped bearers).

Revision ID: 014_phase3_layer3_m2
Revises: 013_phase3_layer3_m1
Create Date: 2026-04-20
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "014_phase3_layer3_m2"
down_revision = "013_phase3_layer3_m1"
branch_labels = None
depends_on = None


STAGE_STATE = "agents_rollout_stage_state"


def upgrade():
    """
        Create the Layer-3 M2 tables.
    """
    op.create_table(
        "agents_rollout_stages",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "rollout_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents_rollouts.rollout_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("rollout_policy", sa.VARCHAR(64), nullable=False),
        sa.Column("target_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "state",
            sa.Enum("PENDING", "ACTIVE", "HELD", "COMPLETED", "HALTED", name=STAGE_STATE),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deferred_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("stage_id"),
        sa.UniqueConstraint("rollout_id", "stage_index", name="uq_agents_rollout_stage_index"),
    )

    op.create_table(
        "agents_pod_pins",
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pinned_version", sa.VARCHAR(64), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reason", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("pod_id"),
    )

    op.create_table(
        "pods_scoped_bearers",
        sa.Column("bearer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ref", sa.VARCHAR(512), nullable=False),
        sa.Column("policy", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("bearer_id"),
    )
    op.create_index("ix_pods_scoped_bearer_run", "pods_scoped_bearers", ["run_id"])

    return


def downgrade():
    """
        Drop Layer-3 M2 tables.
    """
    op.drop_index("ix_pods_scoped_bearer_run", table_name="pods_scoped_bearers")
    op.drop_table("pods_scoped_bearers")
    op.drop_table("agents_pod_pins")
    op.drop_table("agents_rollout_stages")

    bind = op.get_bind()
    sa.Enum(name=STAGE_STATE).drop(bind, checkfirst=True)
    return
