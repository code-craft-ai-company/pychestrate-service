"""
Add Phase-7 / 6-infra-orchestration M1 tables.

Revision ID: 032_phase7_infra_orchestration
Revises: 031_phase7_environment_registry
Create Date: 2026-04-25

Adds:

- ``orch_infra_run``.

Plus the ``orch_infra_action`` and ``orch_infra_run_state``
enums.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "032_phase7_infra_orchestration"
down_revision = "031_phase7_environment_registry"
branch_labels = None
depends_on = None


INFRA_ACTION_ENUM = "orch_infra_action"
INFRA_ACTION_VALUES = ("PLAN", "APPLY", "DESTROY")

INFRA_RUN_STATE_ENUM = "orch_infra_run_state"
INFRA_RUN_STATE_VALUES = (
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "REJECTED_BY_GUARD",
)


def upgrade():
    """
        Create the infra-run table.
    """
    op.create_table(
        "orch_infra_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "environment_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "driver_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "action",
            sa.Enum(*INFRA_ACTION_VALUES, name=INFRA_ACTION_ENUM),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(*INFRA_RUN_STATE_VALUES, name=INFRA_RUN_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "layer5_run_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_role_set_csv",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column("inputs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "inputs_canonical_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("plan_summary", sa.JSON(), nullable=True),
        sa.Column("plan_artifact_ref", sa.Text(), nullable=True),
        sa.Column(
            "plan_diff_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("plan_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_of", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "output_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "failing_guard_rule_id", sa.VARCHAR(128), nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "final_state_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_orch_infra_run_project_env_state",
        "orch_infra_run",
        ["project_id", "environment_id", "state"],
    )
    op.create_index(
        "ix_orch_infra_run_replay_of",
        "orch_infra_run",
        ["replay_of"],
    )
    op.create_index(
        "ix_orch_infra_run_driver_state",
        "orch_infra_run",
        ["driver_name", "state"],
    )
    return


def downgrade():
    """
        Drop the infra-run table and the new enums.
    """
    op.drop_index(
        "ix_orch_infra_run_driver_state", table_name="orch_infra_run",
    )
    op.drop_index(
        "ix_orch_infra_run_replay_of", table_name="orch_infra_run",
    )
    op.drop_index(
        "ix_orch_infra_run_project_env_state", table_name="orch_infra_run",
    )
    op.drop_table("orch_infra_run")

    sa.Enum(name=INFRA_RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=INFRA_ACTION_ENUM).drop(op.get_bind(), checkfirst=True)
    return
