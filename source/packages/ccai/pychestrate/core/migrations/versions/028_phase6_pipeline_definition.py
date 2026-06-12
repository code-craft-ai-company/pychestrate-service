"""
Add Phase-6 / 6-pipeline-definition M1 tables.

Revision ID: 028_phase6_pipeline_definition
Revises: 027_phase5_triage_compare
Create Date: 2026-04-25

Adds:

- ``orch_pipeline_run`` (6-pipeline-definition M1).
- ``orch_pipeline_stage_run`` (6-pipeline-definition M1).
- ``orch_pipeline_step_run`` (6-pipeline-definition M1).
- ``orch_pipeline_document_cache`` (6-pipeline-definition M1).

Plus four new enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "028_phase6_pipeline_definition"
down_revision = "027_phase5_triage_compare"
branch_labels = None
depends_on = None


PIPELINE_RUN_STATE_ENUM = "orch_pipeline_run_state"
PIPELINE_RUN_STATE_VALUES = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "REJECTED",
)

PIPELINE_STAGE_STATE_ENUM = "orch_pipeline_stage_state"
PIPELINE_STAGE_STATE_VALUES = (
    "PENDING", "RUNNING", "SKIPPED", "COMPLETED", "FAILED", "CANCELLED",
)

PIPELINE_STEP_STATE_ENUM = "orch_pipeline_step_state"
PIPELINE_STEP_STATE_VALUES = (
    "PENDING", "DISPATCHED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
    "SKIPPED",
)

PIPELINE_TRIGGER_CAUSE_ENUM = "orch_pipeline_trigger_cause"
PIPELINE_TRIGGER_CAUSE_VALUES = ("MANUAL", "WEBHOOK", "SCHEDULE", "API")


def upgrade():
    """
        Create the pipeline-definition tables.
    """
    op.create_table(
        "orch_pipeline_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commit_sha", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("ref", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("filename", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column(
            "pipeline_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "state",
            sa.Enum(
                *PIPELINE_RUN_STATE_VALUES, name=PIPELINE_RUN_STATE_ENUM,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "trigger_cause",
            sa.Enum(
                *PIPELINE_TRIGGER_CAUSE_VALUES,
                name=PIPELINE_TRIGGER_CAUSE_ENUM,
            ),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        "ix_orch_pipeline_run_project_state",
        "orch_pipeline_run",
        ["project_id", "state"],
    )
    op.create_index(
        "ix_orch_pipeline_run_commit_filename",
        "orch_pipeline_run",
        ["commit_sha", "filename"],
    )
    op.create_index(
        "ix_orch_pipeline_run_digest",
        "orch_pipeline_run",
        ["pipeline_digest_sha256"],
    )

    op.create_table(
        "orch_pipeline_stage_run",
        sa.Column(
            "stage_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "stage_index", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "state",
            sa.Enum(
                *PIPELINE_STAGE_STATE_VALUES, name=PIPELINE_STAGE_STATE_ENUM,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "when_clause",
            sa.VARCHAR(64),
            nullable=False,
            server_default="succeeded",
        ),
        sa.Column(
            "when_clause_resolved",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("needs_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "final_state_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("stage_run_id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["orch_pipeline_run.run_id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_orch_pipeline_stage_run_run",
        "orch_pipeline_stage_run",
        ["run_id"],
    )
    op.create_index(
        "ix_orch_pipeline_stage_run_run_index",
        "orch_pipeline_stage_run",
        ["run_id", "stage_index"],
    )

    op.create_table(
        "orch_pipeline_step_run",
        sa.Column(
            "step_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "stage_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("step_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "step_index", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "kind_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "job_kind", sa.VARCHAR(32), nullable=False, server_default="",
        ),
        sa.Column(
            "layer5_run_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "state",
            sa.Enum(
                *PIPELINE_STEP_STATE_VALUES, name=PIPELINE_STEP_STATE_ENUM,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inputs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "final_state_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("step_run_id"),
        sa.ForeignKeyConstraint(
            ["stage_run_id"],
            ["orch_pipeline_stage_run.stage_run_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_orch_pipeline_step_run_stage",
        "orch_pipeline_step_run",
        ["stage_run_id"],
    )
    op.create_index(
        "ix_orch_pipeline_step_run_layer5",
        "orch_pipeline_step_run",
        ["layer5_run_id"],
    )

    op.create_table(
        "orch_pipeline_document_cache",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commit_sha", sa.VARCHAR(64), nullable=False),
        sa.Column("filename", sa.VARCHAR(256), nullable=False),
        sa.Column(
            "pipeline_digest_sha256", sa.VARCHAR(64), nullable=False,
        ),
        sa.Column(
            "canonical_json", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "commit_sha", "filename",
            name="pk_orch_pipeline_document_cache",
        ),
    )
    op.create_index(
        "ix_orch_pipeline_document_cache_digest",
        "orch_pipeline_document_cache",
        ["pipeline_digest_sha256"],
    )
    return


def downgrade():
    """
        Drop the pipeline-definition tables and the new enums.
    """
    op.drop_index(
        "ix_orch_pipeline_document_cache_digest",
        table_name="orch_pipeline_document_cache",
    )
    op.drop_table("orch_pipeline_document_cache")

    op.drop_index(
        "ix_orch_pipeline_step_run_layer5",
        table_name="orch_pipeline_step_run",
    )
    op.drop_index(
        "ix_orch_pipeline_step_run_stage",
        table_name="orch_pipeline_step_run",
    )
    op.drop_table("orch_pipeline_step_run")

    op.drop_index(
        "ix_orch_pipeline_stage_run_run_index",
        table_name="orch_pipeline_stage_run",
    )
    op.drop_index(
        "ix_orch_pipeline_stage_run_run",
        table_name="orch_pipeline_stage_run",
    )
    op.drop_table("orch_pipeline_stage_run")

    op.drop_index(
        "ix_orch_pipeline_run_digest", table_name="orch_pipeline_run",
    )
    op.drop_index(
        "ix_orch_pipeline_run_commit_filename",
        table_name="orch_pipeline_run",
    )
    op.drop_index(
        "ix_orch_pipeline_run_project_state",
        table_name="orch_pipeline_run",
    )
    op.drop_table("orch_pipeline_run")

    sa.Enum(name=PIPELINE_TRIGGER_CAUSE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PIPELINE_STEP_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PIPELINE_STAGE_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PIPELINE_RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
