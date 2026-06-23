"""
Add Phase-5 / 6-flake-tracking M1 tables.

Revision ID: 026_phase5_flake_tracking
Revises: 025_phase5_matrix_sharding
Create Date: 2026-04-25

Adds:

- ``orch_test_outcome``
- ``orch_flake_classification`` (composite PK on project +
  catalog entry + identity SHA + env digest).
- ``orch_flake_quarantine_ledger``

Plus the ``orch_test_outcome``, ``orch_flake_class``, and
``orch_flake_quarantine_action`` enums.

The 6-artifact-browser feature is registry-only at M1 — no
schema.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "026_phase5_flake_tracking"
down_revision = "025_phase5_matrix_sharding"
branch_labels = None
depends_on = None


OUTCOME_ENUM = "orch_test_outcome"
OUTCOME_VALUES = ("PASS", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS")

FLAKE_CLASS_ENUM = "orch_flake_class"
FLAKE_CLASS_VALUES = (
    "STABLE",
    "INTERMITTENT",
    "FLAKY",
    "QUARANTINED",
    "BROKEN",
    "INSUFFICIENT_DATA",
)

QUARANTINE_ACTION_ENUM = "orch_flake_quarantine_action"
QUARANTINE_ACTION_VALUES = ("QUARANTINE", "CLEAR")


def upgrade():
    """
        Create the flake-tracking tables.
    """
    op.create_table(
        "orch_test_outcome",
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "test_case_identity_sha256", sa.VARCHAR(64), nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "runtime_env_digest",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "outcome",
            sa.Enum(*OUTCOME_VALUES, name=OUTCOME_ENUM),
            nullable=False,
            server_default="PASS",
        ),
        sa.Column(
            "duration_ms", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("outcome_id"),
        sa.UniqueConstraint(
            "run_id", "test_case_identity_sha256",
            name="uq_orch_test_outcome_run_identity",
        ),
    )
    op.create_index(
        "ix_orch_test_outcome_project_entry_started",
        "orch_test_outcome",
        ["project_id", "catalog_entry_id", "started_at"],
    )
    op.create_index(
        "ix_orch_test_outcome_identity_started",
        "orch_test_outcome",
        ["test_case_identity_sha256", "started_at"],
    )

    op.create_table(
        "orch_flake_classification",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "test_case_identity_sha256", sa.VARCHAR(64), nullable=False,
        ),
        sa.Column(
            "runtime_env_digest",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "classification",
            sa.Enum(*FLAKE_CLASS_VALUES, name=FLAKE_CLASS_ENUM),
            nullable=False,
            server_default="INSUFFICIENT_DATA",
        ),
        sa.Column(
            "classifier_name",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "classifier_version",
            sa.VARCHAR(32),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "sample_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "rationale_tag",
            sa.VARCHAR(128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "catalog_entry_id",
            "test_case_identity_sha256",
            "runtime_env_digest",
            name="pk_orch_flake_classification",
        ),
    )
    op.create_index(
        "ix_orch_flake_classification_entry_class",
        "orch_flake_classification",
        ["catalog_entry_id", "classification"],
    )

    op.create_table(
        "orch_flake_quarantine_ledger",
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "test_case_identity_sha256", sa.VARCHAR(64), nullable=False,
        ),
        sa.Column(
            "runtime_env_digest",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "action",
            sa.Enum(
                *QUARANTINE_ACTION_VALUES, name=QUARANTINE_ACTION_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "at_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ledger_id"),
    )
    op.create_index(
        "ix_orch_flake_quarantine_ledger_target_at",
        "orch_flake_quarantine_ledger",
        ["test_case_identity_sha256", "at_ts"],
    )
    return


def downgrade():
    """
        Drop the flake-tracking tables and the new enums.
    """
    op.drop_index(
        "ix_orch_flake_quarantine_ledger_target_at",
        table_name="orch_flake_quarantine_ledger",
    )
    op.drop_table("orch_flake_quarantine_ledger")

    op.drop_index(
        "ix_orch_flake_classification_entry_class",
        table_name="orch_flake_classification",
    )
    op.drop_table("orch_flake_classification")

    op.drop_index(
        "ix_orch_test_outcome_identity_started",
        table_name="orch_test_outcome",
    )
    op.drop_index(
        "ix_orch_test_outcome_project_entry_started",
        table_name="orch_test_outcome",
    )
    op.drop_table("orch_test_outcome")

    sa.Enum(name=QUARANTINE_ACTION_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=FLAKE_CLASS_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    return
