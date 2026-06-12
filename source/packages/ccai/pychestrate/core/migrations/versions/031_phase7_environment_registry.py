"""
Add Phase-7 / 6-environment-registry M1 tables.

Revision ID: 031_phase7_environment_registry
Revises: 030_phase6_build_orchestration_artifacts
Create Date: 2026-04-25

Adds:

- ``orch_environment``.
- ``orch_environment_history``.

Plus the ``orch_environment_state`` and
``orch_environment_event_kind`` enums.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "031_phase7_environment_registry"
down_revision = "030_phase6_build_orchestration_artifacts"
branch_labels = None
depends_on = None


ENVIRONMENT_STATE_ENUM = "orch_environment_state"
ENVIRONMENT_STATE_VALUES = ("ACTIVE", "FROZEN", "ARCHIVED", "DESTROYED")

ENVIRONMENT_EVENT_KIND_ENUM = "orch_environment_event_kind"
ENVIRONMENT_EVENT_KIND_VALUES = (
    "DECLARED",
    "UPDATED",
    "ARCHIVED",
    "FROZEN",
    "UNFROZEN",
    "APPLIED",
    "DESTROYED",
)


def upgrade():
    """
        Create the environment-registry tables.
    """
    op.create_table(
        "orch_environment",
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column("name", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.Enum(*ENVIRONMENT_STATE_VALUES, name=ENVIRONMENT_STATE_ENUM),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("attrs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("frozen_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("frozen_reason", sa.Text(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_applied_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "last_output_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_reason", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("environment_id"),
        sa.UniqueConstraint(
            "project_id", "kind_name", "name",
            name="uq_orch_environment_project_kind_name",
        ),
    )
    op.create_index(
        "ix_orch_environment_project_kind",
        "orch_environment",
        ["project_id", "kind_name"],
    )
    op.create_index(
        "ix_orch_environment_project_state",
        "orch_environment",
        ["project_id", "state"],
    )

    op.create_table(
        "orch_environment_history",
        sa.Column("history_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "event_kind",
            sa.Enum(
                *ENVIRONMENT_EVENT_KIND_VALUES,
                name=ENVIRONMENT_EVENT_KIND_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "at_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("history_id"),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["orch_environment.environment_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_orch_environment_history_env_at",
        "orch_environment_history",
        ["environment_id", "at_ts"],
    )
    return


def downgrade():
    """
        Drop the environment-registry tables and the new enums.
    """
    op.drop_index(
        "ix_orch_environment_history_env_at",
        table_name="orch_environment_history",
    )
    op.drop_table("orch_environment_history")

    op.drop_index(
        "ix_orch_environment_project_state",
        table_name="orch_environment",
    )
    op.drop_index(
        "ix_orch_environment_project_kind",
        table_name="orch_environment",
    )
    op.drop_table("orch_environment")

    sa.Enum(name=ENVIRONMENT_EVENT_KIND_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=ENVIRONMENT_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
