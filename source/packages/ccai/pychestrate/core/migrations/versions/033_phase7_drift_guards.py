"""
Add Phase-7 / 6-drift-detection + 6-blast-radius-guards M1
tables.

Revision ID: 033_phase7_drift_guards
Revises: 032_phase7_infra_orchestration
Create Date: 2026-04-25

Adds (drift):

- ``orch_drift_schedule`` (composite PK on
  ``(project_id, environment_id)``).
- ``orch_drift_run``.
- ``orch_drift_tick_ledger`` (composite PK on
  ``(project_id, environment_id, scheduled_for)``).

Adds (guards):

- ``orch_guard_attachment`` (composite PK on
  ``(project_id, environment_id, rule_id)``).

Plus the ``orch_drift_run_state`` and
``orch_drift_trigger_kind`` enums.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "033_phase7_drift_guards"
down_revision = "032_phase7_infra_orchestration"
branch_labels = None
depends_on = None


DRIFT_RUN_STATE_ENUM = "orch_drift_run_state"
DRIFT_RUN_STATE_VALUES = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED",
    "INGEST_FAILED", "SKIPPED",
)

DRIFT_TRIGGER_KIND_ENUM = "orch_drift_trigger_kind"
DRIFT_TRIGGER_KIND_VALUES = ("SCHEDULE", "MANUAL")


def upgrade():
    """
        Create the drift + guards tables.
    """
    op.create_table(
        "orch_drift_schedule",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "checker_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "cron_expression",
            sa.VARCHAR(128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "environment_id",
            name="pk_orch_drift_schedule",
        ),
    )

    op.create_table(
        "orch_drift_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "checker_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "layer5_run_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "state",
            sa.Enum(*DRIFT_RUN_STATE_VALUES, name=DRIFT_RUN_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "trigger_kind",
            sa.Enum(
                *DRIFT_TRIGGER_KIND_VALUES, name=DRIFT_TRIGGER_KIND_ENUM,
            ),
            nullable=False,
        ),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drift_count", sa.Integer(), nullable=True),
        sa.Column("added", sa.Integer(), nullable=True),
        sa.Column("changed", sa.Integer(), nullable=True),
        sa.Column("destroyed", sa.Integer(), nullable=True),
        sa.Column(
            "diff_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("report_blob_key", sa.Text(), nullable=True),
        sa.Column("report_payload", sa.JSON(), nullable=True),
        sa.Column(
            "final_state_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_orch_drift_run_env_scheduled",
        "orch_drift_run",
        ["environment_id", "scheduled_for"],
    )
    op.create_index(
        "ix_orch_drift_run_state",
        "orch_drift_run",
        ["state"],
    )

    op.create_table(
        "orch_drift_tick_ledger",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "environment_id", "scheduled_for",
            name="pk_orch_drift_tick_ledger",
        ),
    )

    op.create_table(
        "orch_guard_attachment",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("rule_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "added_at",
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
        sa.PrimaryKeyConstraint(
            "project_id", "environment_id", "rule_id",
            name="pk_orch_guard_attachment",
        ),
    )
    op.create_index(
        "ix_orch_guard_attachment_env_enabled",
        "orch_guard_attachment",
        ["environment_id", "enabled"],
    )
    return


def downgrade():
    """
        Drop the drift + guards tables and the new enums.
    """
    op.drop_index(
        "ix_orch_guard_attachment_env_enabled",
        table_name="orch_guard_attachment",
    )
    op.drop_table("orch_guard_attachment")

    op.drop_table("orch_drift_tick_ledger")
    op.drop_index(
        "ix_orch_drift_run_state", table_name="orch_drift_run",
    )
    op.drop_index(
        "ix_orch_drift_run_env_scheduled", table_name="orch_drift_run",
    )
    op.drop_table("orch_drift_run")
    op.drop_table("orch_drift_schedule")

    sa.Enum(name=DRIFT_TRIGGER_KIND_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=DRIFT_RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
