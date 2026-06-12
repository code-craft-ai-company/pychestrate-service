"""
Add Phase 3 / Layer-6 test-catalog + test-orchestration tables.

Revision ID: 020_phase3_test_orchestration
Revises: 019_phase3_results_ingest
Create Date: 2026-04-24

Adds:

- ``orchestration_test_catalog_entry`` — registered test suites,
  unique on ``(project_id, importer_tag, entry_key)``.
- ``orchestration_test_run`` — orchestration trigger row.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "020_phase3_test_orchestration"
down_revision = "019_phase3_results_ingest"
branch_labels = None
depends_on = None


TEST_RUN_STATE_ENUM = "orchestration_test_run_state"
TEST_RUN_STATE_VALUES = (
    "TRIGGERED",
    "DISPATCHING",
    "DISPATCHED",
    "DISPATCH_FAILED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "NEEDS_INVESTIGATION",
    "INELIGIBLE",
)


def upgrade():
    """
        Create the catalog entry + test run tables.
    """
    op.create_table(
        "orchestration_test_catalog_entry",
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("importer_tag", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("entry_key", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("display_name", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("required_capability_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("param_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("raw_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("canonical_digest", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint(
            "project_id", "importer_tag", "entry_key",
            name="uq_orchestration_test_catalog_entry_id_keys",
        ),
    )
    op.create_index(
        "ix_orchestration_test_catalog_entry_project",
        "orchestration_test_catalog_entry",
        ["project_id"],
    )
    op.create_index(
        "ix_orchestration_test_catalog_entry_retired",
        "orchestration_test_catalog_entry",
        ["retired"],
    )

    op.create_table(
        "orchestration_test_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_kind", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            sa.Enum(*TEST_RUN_STATE_VALUES, name=TEST_RUN_STATE_ENUM),
            nullable=False,
            server_default="TRIGGERED",
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("inputs_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_orchestration_test_run_project",
        "orchestration_test_run",
        ["project_id"],
    )
    op.create_index(
        "ix_orchestration_test_run_state",
        "orchestration_test_run",
        ["state"],
    )
    op.create_index(
        "ix_orchestration_test_run_catalog_entry",
        "orchestration_test_run",
        ["catalog_entry_id"],
    )
    return


def downgrade():
    """
        Drop the test orchestration tables and enum.
    """
    op.drop_index("ix_orchestration_test_run_catalog_entry", table_name="orchestration_test_run")
    op.drop_index("ix_orchestration_test_run_state", table_name="orchestration_test_run")
    op.drop_index("ix_orchestration_test_run_project", table_name="orchestration_test_run")
    op.drop_table("orchestration_test_run")

    op.drop_index(
        "ix_orchestration_test_catalog_entry_retired",
        table_name="orchestration_test_catalog_entry",
    )
    op.drop_index(
        "ix_orchestration_test_catalog_entry_project",
        table_name="orchestration_test_catalog_entry",
    )
    op.drop_table("orchestration_test_catalog_entry")

    sa.Enum(name=TEST_RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
