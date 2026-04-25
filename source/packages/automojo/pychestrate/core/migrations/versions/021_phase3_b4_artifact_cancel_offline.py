"""
Add Phase 3 / Layer-5 B4 tables — artifact + cancel + offline.

Revision ID: 021_phase3_b4_artifact_cancel_offline
Revises: 020_phase3_test_orchestration
Create Date: 2026-04-24

Adds:

5-artifact-store (4):
- ``artifacts_artifact_blob``
- ``artifacts_run_artifact_reference``
- ``artifacts_artifact_type_metadata``
- ``artifacts_artifact_retention_plan``

5-cancel-reconcile (2):
- ``jobs_cancel_request``
- ``jobs_reconcile_decision``

5-offline-tolerance (3):
- ``jobs_pod_offline_state``
- ``jobs_client_replay_cursor``
- ``jobs_deferred_cancel``

Plus the four enums backing the lifecycle columns.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "021_phase3_b4_artifact_cancel_offline"
down_revision = "020_phase3_test_orchestration"
branch_labels = None
depends_on = None


CANCEL_STATUS_ENUM = "jobs_cancel_status"
CANCEL_STATUS_VALUES = ("PENDING", "TRANSMITTED", "ACKED", "FAILED", "QUEUED_OFFLINE")

RECONCILE_OUTCOME_ENUM = "jobs_reconcile_outcome"
RECONCILE_OUTCOME_VALUES = ("NO_CHANGE", "DIVERGENCE_RESOLVED", "PROGRESS_RESUMED", "NEEDS_INVESTIGATION")

POD_LIVENESS_TIER_ENUM = "jobs_offline_pod_liveness_tier"
POD_LIVENESS_TIER_VALUES = ("HEALTHY", "DEGRADED", "OFFLINE")

DEFERRED_CANCEL_STATUS_ENUM = "jobs_offline_deferred_cancel_status"
DEFERRED_CANCEL_STATUS_VALUES = ("QUEUED", "DELIVERED", "EXPIRED")


def upgrade():
    """
        Create the nine tables in dependency-friendly order.
    """
    # 5-artifact-store
    op.create_table(
        "artifacts_artifact_blob",
        sa.Column("cas_digest", sa.VARCHAR(64), nullable=False),
        sa.Column("cas_key", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("backend_driver", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.VARCHAR(128), nullable=True),
        sa.Column("reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tier", sa.VARCHAR(16), nullable=False, server_default="hot"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_referenced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("cas_digest"),
    )
    op.create_table(
        "artifacts_run_artifact_reference",
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("artifact_type", sa.VARCHAR(64), nullable=False, server_default="generic"),
        sa.Column("cas_digest", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("reference_id"),
        sa.UniqueConstraint(
            "run_id", "label",
            name="uq_artifacts_run_reference_run_label",
        ),
    )
    op.create_index("ix_artifacts_run_reference_run", "artifacts_run_artifact_reference", ["run_id"])
    op.create_index("ix_artifacts_run_reference_digest", "artifacts_run_artifact_reference", ["cas_digest"])

    op.create_table(
        "artifacts_artifact_type_metadata",
        sa.Column("artifact_type", sa.VARCHAR(64), nullable=False),
        sa.Column("description", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("schema_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("artifact_type"),
    )

    op.create_table(
        "artifacts_artifact_retention_plan",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cas_digest", sa.VARCHAR(64), nullable=False),
        sa.Column("target_tier", sa.VARCHAR(16), nullable=False, server_default="cold"),
        sa.Column("apply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_index(
        "ix_artifacts_retention_plan_digest",
        "artifacts_artifact_retention_plan",
        ["cas_digest"],
    )

    # 5-cancel-reconcile
    op.create_table(
        "jobs_cancel_request",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(*CANCEL_STATUS_VALUES, name=CANCEL_STATUS_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("transmitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_jobs_cancel_request_run", "jobs_cancel_request", ["run_id"])
    op.create_index("ix_jobs_cancel_request_status", "jobs_cancel_request", ["status"])

    op.create_table(
        "jobs_reconcile_decision",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prior_state", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("resolved_state", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column(
            "outcome",
            sa.Enum(*RECONCILE_OUTCOME_VALUES, name=RECONCILE_OUTCOME_ENUM),
            nullable=False,
            server_default="NO_CHANGE",
        ),
        sa.Column("source", sa.VARCHAR(64), nullable=False, server_default="client_truth"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_jobs_reconcile_decision_run", "jobs_reconcile_decision", ["run_id"])
    op.create_index(
        "ix_jobs_reconcile_decision_outcome",
        "jobs_reconcile_decision",
        ["outcome"],
    )

    # 5-offline-tolerance
    op.create_table(
        "jobs_pod_offline_state",
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tier",
            sa.Enum(*POD_LIVENESS_TIER_VALUES, name=POD_LIVENESS_TIER_ENUM),
            nullable=False,
            server_default="HEALTHY",
        ),
        sa.Column("last_session_dropped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("pod_id"),
    )
    op.create_index("ix_jobs_pod_offline_state_tier", "jobs_pod_offline_state", ["tier"])

    op.create_table(
        "jobs_client_replay_cursor",
        sa.Column("cursor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("next_expected_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("cursor_id"),
        sa.UniqueConstraint(
            "client_id", "run_id",
            name="uq_jobs_client_replay_cursor_client_run",
        ),
    )

    op.create_table(
        "jobs_deferred_cancel",
        sa.Column("deferred_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cancel_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(*DEFERRED_CANCEL_STATUS_VALUES, name=DEFERRED_CANCEL_STATUS_ENUM),
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("deferred_id"),
    )
    op.create_index("ix_jobs_deferred_cancel_pod", "jobs_deferred_cancel", ["pod_id"])
    op.create_index("ix_jobs_deferred_cancel_status", "jobs_deferred_cancel", ["status"])
    op.create_index("ix_jobs_deferred_cancel_run", "jobs_deferred_cancel", ["run_id"])
    return


def downgrade():
    """
        Drop the nine tables + four enums in reverse order.
    """
    op.drop_index("ix_jobs_deferred_cancel_run", table_name="jobs_deferred_cancel")
    op.drop_index("ix_jobs_deferred_cancel_status", table_name="jobs_deferred_cancel")
    op.drop_index("ix_jobs_deferred_cancel_pod", table_name="jobs_deferred_cancel")
    op.drop_table("jobs_deferred_cancel")

    op.drop_table("jobs_client_replay_cursor")

    op.drop_index("ix_jobs_pod_offline_state_tier", table_name="jobs_pod_offline_state")
    op.drop_table("jobs_pod_offline_state")

    op.drop_index("ix_jobs_reconcile_decision_outcome", table_name="jobs_reconcile_decision")
    op.drop_index("ix_jobs_reconcile_decision_run", table_name="jobs_reconcile_decision")
    op.drop_table("jobs_reconcile_decision")

    op.drop_index("ix_jobs_cancel_request_status", table_name="jobs_cancel_request")
    op.drop_index("ix_jobs_cancel_request_run", table_name="jobs_cancel_request")
    op.drop_table("jobs_cancel_request")

    op.drop_index(
        "ix_artifacts_retention_plan_digest",
        table_name="artifacts_artifact_retention_plan",
    )
    op.drop_table("artifacts_artifact_retention_plan")

    op.drop_table("artifacts_artifact_type_metadata")

    op.drop_index(
        "ix_artifacts_run_reference_digest",
        table_name="artifacts_run_artifact_reference",
    )
    op.drop_index(
        "ix_artifacts_run_reference_run",
        table_name="artifacts_run_artifact_reference",
    )
    op.drop_table("artifacts_run_artifact_reference")

    op.drop_table("artifacts_artifact_blob")

    sa.Enum(name=DEFERRED_CANCEL_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=POD_LIVENESS_TIER_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RECONCILE_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=CANCEL_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    return
