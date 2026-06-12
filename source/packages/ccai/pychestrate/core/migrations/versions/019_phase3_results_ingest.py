"""
Add Phase 3 / Layer-5 results + ingest tables.

Revision ID: 019_phase3_results_ingest
Revises: 018_phase3_dispatch_receipt
Create Date: 2026-04-24

Adds eight tables across three features:

5-shared-results-backend:
- ``jobs_shared_results_allocation``

5-progress-ingest:
- ``ingest_run_progress_summary``
- ``ingest_run_progress_record``
- ``ingest_run_progress_counters``

5-result-ingest-watcher:
- ``ingest_run_result_summary``
- ``ingest_task_result``
- ``ingest_run_artifact``
- ``ingest_result_scan_attempt``
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "019_phase3_results_ingest"
down_revision = "018_phase3_dispatch_receipt"
branch_labels = None
depends_on = None


SCAN_OUTCOME_STATUS_ENUM = "ingest_scan_outcome_status"
SCAN_OUTCOME_STATUS_VALUES = ("SCANNED", "NOT_FOUND", "FAILED")


def upgrade():
    """
        Create the eight new tables in dependency-friendly order
        (allocation first, then progress tables, then result
        tables).
    """
    op.create_table(
        "jobs_shared_results_allocation",
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("backend_driver", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("backend_key_prefix", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "allocated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("allocation_id"),
        sa.UniqueConstraint("run_id", name="uq_jobs_shared_results_allocation_run"),
    )
    op.create_index(
        "ix_jobs_shared_results_allocation_project_id",
        "jobs_shared_results_allocation",
        ["project_id"],
    )

    op.create_table(
        "ingest_run_progress_summary",
        sa.Column("summary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("format_tag", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("tests_total", sa.Integer(), nullable=True),
        sa.Column("tests_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_errored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percent_complete", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("summary_id"),
    )
    op.create_index(
        "ix_ingest_run_progress_summary_run_id",
        "ingest_run_progress_summary",
        ["run_id"],
    )
    op.create_index(
        "ix_ingest_run_progress_summary_received_at",
        "ingest_run_progress_summary",
        ["received_at"],
    )

    op.create_table(
        "ingest_run_progress_record",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=False),
        sa.Column("test_name", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("result", sa.VARCHAR(32), nullable=False, server_default="UNSET"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "run_id", "record_index",
            name="uq_ingest_run_progress_record_run_index",
        ),
    )
    op.create_index(
        "ix_ingest_run_progress_record_run_id",
        "ingest_run_progress_record",
        ["run_id"],
    )
    op.create_index(
        "ix_ingest_run_progress_record_result",
        "ingest_run_progress_record",
        ["result"],
    )

    op.create_table(
        "ingest_run_progress_counters",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tests_total", sa.Integer(), nullable=True),
        sa.Column("tests_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_errored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percent_complete", sa.Float(), nullable=True),
        sa.Column("last_summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_ingest_run_progress_counters_project_id",
        "ingest_run_progress_counters",
        ["project_id"],
    )

    op.create_table(
        "ingest_run_result_summary",
        sa.Column("summary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parser_tag", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("tests_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_errored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("summary_id"),
        sa.UniqueConstraint("run_id", name="uq_ingest_run_result_summary_run"),
    )
    op.create_index(
        "ix_ingest_run_result_summary_project",
        "ingest_run_result_summary",
        ["project_id"],
    )

    op.create_table(
        "ingest_task_result",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_name", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("instance_uuid", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("rtype", sa.VARCHAR(32), nullable=False, server_default="TEST"),
        sa.Column("result", sa.VARCHAR(32), nullable=False, server_default="UNSET"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint(
            "run_id", "instance_uuid",
            name="uq_ingest_task_result_run_instance",
        ),
    )
    op.create_index("ix_ingest_task_result_run", "ingest_task_result", ["run_id"])
    op.create_index("ix_ingest_task_result_result", "ingest_task_result", ["result"])

    op.create_table(
        "ingest_run_artifact",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relative_path", sa.VARCHAR(1024), nullable=False, server_default=""),
        sa.Column("classification", sa.VARCHAR(64), nullable=False, server_default="other"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.VARCHAR(128), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.UniqueConstraint(
            "run_id", "relative_path",
            name="uq_ingest_run_artifact_run_path",
        ),
    )
    op.create_index("ix_ingest_run_artifact_run", "ingest_run_artifact", ["run_id"])
    op.create_index(
        "ix_ingest_run_artifact_classification",
        "ingest_run_artifact",
        ["classification"],
    )

    op.create_table(
        "ingest_result_scan_attempt",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*SCAN_OUTCOME_STATUS_VALUES, name=SCAN_OUTCOME_STATUS_ENUM),
            nullable=False,
            server_default="SCANNED",
        ),
        sa.Column("files_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifacts_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_ingest_result_scan_attempt_run",
        "ingest_result_scan_attempt",
        ["run_id"],
    )
    op.create_index(
        "ix_ingest_result_scan_attempt_status",
        "ingest_result_scan_attempt",
        ["status"],
    )
    return


def downgrade():
    """
        Drop the eight tables in reverse order.
    """
    op.drop_index("ix_ingest_result_scan_attempt_status", table_name="ingest_result_scan_attempt")
    op.drop_index("ix_ingest_result_scan_attempt_run", table_name="ingest_result_scan_attempt")
    op.drop_table("ingest_result_scan_attempt")

    op.drop_index("ix_ingest_run_artifact_classification", table_name="ingest_run_artifact")
    op.drop_index("ix_ingest_run_artifact_run", table_name="ingest_run_artifact")
    op.drop_table("ingest_run_artifact")

    op.drop_index("ix_ingest_task_result_result", table_name="ingest_task_result")
    op.drop_index("ix_ingest_task_result_run", table_name="ingest_task_result")
    op.drop_table("ingest_task_result")

    op.drop_index("ix_ingest_run_result_summary_project", table_name="ingest_run_result_summary")
    op.drop_table("ingest_run_result_summary")

    op.drop_index(
        "ix_ingest_run_progress_counters_project_id",
        table_name="ingest_run_progress_counters",
    )
    op.drop_table("ingest_run_progress_counters")

    op.drop_index(
        "ix_ingest_run_progress_record_result",
        table_name="ingest_run_progress_record",
    )
    op.drop_index(
        "ix_ingest_run_progress_record_run_id",
        table_name="ingest_run_progress_record",
    )
    op.drop_table("ingest_run_progress_record")

    op.drop_index(
        "ix_ingest_run_progress_summary_received_at",
        table_name="ingest_run_progress_summary",
    )
    op.drop_index(
        "ix_ingest_run_progress_summary_run_id",
        table_name="ingest_run_progress_summary",
    )
    op.drop_table("ingest_run_progress_summary")

    op.drop_index(
        "ix_jobs_shared_results_allocation_project_id",
        table_name="jobs_shared_results_allocation",
    )
    op.drop_table("jobs_shared_results_allocation")

    sa.Enum(name=SCAN_OUTCOME_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    return
