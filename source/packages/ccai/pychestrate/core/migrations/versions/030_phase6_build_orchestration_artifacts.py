"""
Add Phase-6 / 6-build-orchestration + 6-build-artifacts M1 tables.

Revision ID: 030_phase6_build_orchestration_artifacts
Revises: 029_phase6_source_integrations
Create Date: 2026-04-25

Adds (build orchestration):

- ``orch_build_run``.
- ``orch_build_toolchain_snapshot`` (composite PK on
  ``(run_id, toolchain_key)``).
- ``orch_build_cache_scope``.

Adds (build artifacts):

- ``orch_build_artifact_manifest`` (UNIQUE on build_run_id).
- ``orch_build_artifact_entry_index`` (composite PK on
  ``(manifest_id, artifact_id)``).
- ``orch_build_artifact_promotion_ledger``.
- ``orch_build_artifact_channel_head`` (composite PK on
  ``(project_id, channel, artifact_id)``).

Plus the ``orch_build_run_state`` and
``orch_build_artifact_promotion_action`` enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "030_phase6_build_orchestration_artifacts"
down_revision = "029_phase6_source_integrations"
branch_labels = None
depends_on = None


BUILD_RUN_STATE_ENUM = "orch_build_run_state"
BUILD_RUN_STATE_VALUES = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
)

PROMOTION_ACTION_ENUM = "orch_build_artifact_promotion_action"
PROMOTION_ACTION_VALUES = ("PROMOTE", "ROLLBACK")


def upgrade():
    """
        Create the build-orchestration + build-artifacts tables.
    """
    op.create_table(
        "orch_build_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "runner_kind", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "repro_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "state",
            sa.Enum(*BUILD_RUN_STATE_VALUES, name=BUILD_RUN_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "layer5_run_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "pipeline_step_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
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
        sa.Column("inputs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "annotations", sa.JSON(), nullable=False, server_default="{}",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_orch_build_run_project_state",
        "orch_build_run",
        ["project_id", "state"],
    )
    op.create_index(
        "ix_orch_build_run_digest",
        "orch_build_run",
        ["repro_digest_sha256"],
    )
    op.create_index(
        "ix_orch_build_run_layer5",
        "orch_build_run",
        ["layer5_run_id"],
    )

    op.create_table(
        "orch_build_toolchain_snapshot",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("toolchain_key", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "version", sa.VARCHAR(128), nullable=False, server_default="",
        ),
        sa.Column(
            "fingerprint_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "toolchain_key",
            name="pk_orch_build_toolchain_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["orch_build_run.run_id"], ondelete="CASCADE",
        ),
    )

    op.create_table(
        "orch_build_cache_scope",
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scope_name", sa.VARCHAR(128), nullable=False, server_default="",
        ),
        sa.Column(
            "bytes_allocated",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("scope_id"),
    )
    op.create_index(
        "ix_orch_build_cache_scope_project",
        "orch_build_cache_scope",
        ["project_id"],
    )

    op.create_table(
        "orch_build_artifact_manifest",
        sa.Column(
            "manifest_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "build_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "entry_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "synthesized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("manifest_id"),
        sa.UniqueConstraint(
            "build_run_id",
            name="uq_orch_build_artifact_manifest_build_run",
        ),
    )
    op.create_index(
        "ix_orch_build_artifact_manifest_project",
        "orch_build_artifact_manifest",
        ["project_id"],
    )

    op.create_table(
        "orch_build_artifact_entry_index",
        sa.Column(
            "manifest_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("artifact_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "artifact_type",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "artifact_name",
            sa.VARCHAR(256),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "storage_uri", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "sha256", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint(
            "manifest_id", "artifact_id",
            name="pk_orch_build_artifact_entry_index",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["orch_build_artifact_manifest.manifest_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_orch_build_artifact_entry_index_artifact",
        "orch_build_artifact_entry_index",
        ["artifact_id", "artifact_type"],
    )

    op.create_table(
        "orch_build_artifact_promotion_ledger",
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "manifest_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.VARCHAR(128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "channel", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "action",
            sa.Enum(*PROMOTION_ACTION_VALUES, name=PROMOTION_ACTION_ENUM),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "at_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ledger_id"),
    )
    op.create_index(
        "ix_orch_build_artifact_promotion_ledger_artifact",
        "orch_build_artifact_promotion_ledger",
        ["artifact_id", "channel"],
    )

    op.create_table(
        "orch_build_artifact_channel_head",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.VARCHAR(64), nullable=False),
        sa.Column("artifact_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "manifest_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "promoted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "channel", "artifact_id",
            name="pk_orch_build_artifact_channel_head",
        ),
    )
    return


def downgrade():
    """
        Drop the build-orchestration + build-artifacts tables
        and the new enums.
    """
    op.drop_table("orch_build_artifact_channel_head")
    op.drop_index(
        "ix_orch_build_artifact_promotion_ledger_artifact",
        table_name="orch_build_artifact_promotion_ledger",
    )
    op.drop_table("orch_build_artifact_promotion_ledger")
    op.drop_index(
        "ix_orch_build_artifact_entry_index_artifact",
        table_name="orch_build_artifact_entry_index",
    )
    op.drop_table("orch_build_artifact_entry_index")
    op.drop_index(
        "ix_orch_build_artifact_manifest_project",
        table_name="orch_build_artifact_manifest",
    )
    op.drop_table("orch_build_artifact_manifest")

    op.drop_index(
        "ix_orch_build_cache_scope_project",
        table_name="orch_build_cache_scope",
    )
    op.drop_table("orch_build_cache_scope")
    op.drop_table("orch_build_toolchain_snapshot")

    op.drop_index(
        "ix_orch_build_run_layer5", table_name="orch_build_run",
    )
    op.drop_index(
        "ix_orch_build_run_digest", table_name="orch_build_run",
    )
    op.drop_index(
        "ix_orch_build_run_project_state", table_name="orch_build_run",
    )
    op.drop_table("orch_build_run")

    sa.Enum(name=PROMOTION_ACTION_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=BUILD_RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
