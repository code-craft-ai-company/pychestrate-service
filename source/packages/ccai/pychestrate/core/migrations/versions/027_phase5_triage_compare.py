"""
Add Phase-5 / 6-triage-bug-linking + 6-compare-runs M1 tables.

Revision ID: 027_phase5_triage_compare
Revises: 026_phase5_flake_tracking
Create Date: 2026-04-25

Adds:

- ``orch_triage_case`` (6-triage-bug-linking M1).
- ``orch_triage_case_ledger`` (6-triage-bug-linking M1).
- ``orch_compare_report`` (6-compare-runs M1).

Plus the ``orch_triage_class`` and ``orch_compare_status``
enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027_phase5_triage_compare"
down_revision = "026_phase5_flake_tracking"
branch_labels = None
depends_on = None


TRIAGE_CLASS_ENUM = "orch_triage_class"
TRIAGE_CLASS_VALUES = ("KNOWN_ISSUE", "NEW_BUG", "INFRA_FLAKE", "OTHER")

COMPARE_STATUS_ENUM = "orch_compare_status"
COMPARE_STATUS_VALUES = ("BUILDING", "READY", "STALE")


def upgrade():
    """
        Create the triage + compare-report tables.
    """
    op.create_table(
        "orch_triage_case",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "test_case_identity_sha256", sa.VARCHAR(64), nullable=False,
        ),
        sa.Column(
            "stack_signature_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "classification",
            sa.Enum(*TRIAGE_CLASS_VALUES, name=TRIAGE_CLASS_ENUM),
            nullable=False,
            server_default="OTHER",
        ),
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default="0.0",
        ),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "classifier_name",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("tracker", sa.VARCHAR(64), nullable=True),
        sa.Column("ticket_key", sa.VARCHAR(128), nullable=True),
        sa.Column("ticket_url", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index(
        "ix_orch_triage_case_run", "orch_triage_case", ["run_id"],
    )
    op.create_index(
        "ix_orch_triage_case_project_class",
        "orch_triage_case",
        ["project_id", "classification"],
    )
    op.create_index(
        "ix_orch_triage_case_signature",
        "orch_triage_case",
        ["stack_signature_sha256"],
    )

    op.create_table(
        "orch_triage_case_ledger",
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "from_class",
            sa.Enum(*TRIAGE_CLASS_VALUES, name=TRIAGE_CLASS_ENUM),
            nullable=True,
        ),
        sa.Column(
            "to_class",
            sa.Enum(*TRIAGE_CLASS_VALUES, name=TRIAGE_CLASS_ENUM),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "at_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ledger_id"),
    )
    op.create_index(
        "ix_orch_triage_case_ledger_case_at",
        "orch_triage_case_ledger",
        ["case_id", "at_ts"],
    )

    op.create_table(
        "orch_compare_report",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "base_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "candidate_run_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(*COMPARE_STATUS_VALUES, name=COMPARE_STATUS_ENUM),
            nullable=False,
            server_default="BUILDING",
        ),
        sa.Column(
            "per_test_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "per_test_payload", sa.JSON(), nullable=False, server_default="[]",
        ),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("report_id"),
        sa.UniqueConstraint(
            "base_run_id", "candidate_run_id",
            name="uq_orch_compare_report_run_pair",
        ),
    )
    op.create_index(
        "ix_orch_compare_report_project",
        "orch_compare_report",
        ["project_id"],
    )
    return


def downgrade():
    """
        Drop the triage + compare tables and the new enums.
    """
    op.drop_index(
        "ix_orch_compare_report_project", table_name="orch_compare_report",
    )
    op.drop_table("orch_compare_report")

    op.drop_index(
        "ix_orch_triage_case_ledger_case_at",
        table_name="orch_triage_case_ledger",
    )
    op.drop_table("orch_triage_case_ledger")

    op.drop_index(
        "ix_orch_triage_case_signature", table_name="orch_triage_case",
    )
    op.drop_index(
        "ix_orch_triage_case_project_class", table_name="orch_triage_case",
    )
    op.drop_index(
        "ix_orch_triage_case_run", table_name="orch_triage_case",
    )
    op.drop_table("orch_triage_case")

    sa.Enum(name=COMPARE_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=TRIAGE_CLASS_ENUM).drop(op.get_bind(), checkfirst=True)
    return
