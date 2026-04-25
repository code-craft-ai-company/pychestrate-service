"""
Add Phase 3 / Layer-5 dispatch + receipt tables.

Revision ID: 018_phase3_dispatch_receipt
Revises: 017_phase3_run_state
Create Date: 2026-04-24

Adds:

- ``jobs_dispatch_attempt`` — one row per transmit attempt. Status
  enum tracks the transport-level lifecycle distinct from the
  run's state machine.
- ``jobs_dispatch_receipt`` — one row per acknowledgment the
  client produced. Unique on
  ``(client_id, client_local_run_id)`` so retries are idempotent.

Chain: extends the single-head chain ``017_phase3_run_state``
that PR #7 established after merging the 015/016 fork.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "018_phase3_dispatch_receipt"
down_revision = "017_phase3_run_state"
branch_labels = None
depends_on = None


DISPATCH_ATTEMPT_STATUS_ENUM = "dispatch_attempt_status"


DISPATCH_ATTEMPT_STATUS_VALUES = (
    "PENDING",
    "TRANSMITTED",
    "ACKED",
    "TRANSPORT_FAILED",
    "ACK_TIMEOUT",
    "ABORTED",
)


def upgrade():
    """
        Create ``jobs_dispatch_attempt`` + ``jobs_dispatch_receipt``
        plus indexes.
    """
    op.create_table(
        "jobs_dispatch_attempt",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_name", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("transport_name", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(*DISPATCH_ATTEMPT_STATUS_VALUES, name=DISPATCH_ATTEMPT_STATUS_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("transmitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_jobs_dispatch_attempt_run_id",
        "jobs_dispatch_attempt",
        ["run_id"],
    )
    op.create_index(
        "ix_jobs_dispatch_attempt_client_id",
        "jobs_dispatch_attempt",
        ["client_id"],
    )
    op.create_index(
        "ix_jobs_dispatch_attempt_status",
        "jobs_dispatch_attempt",
        ["status"],
    )
    op.create_index(
        "ix_jobs_dispatch_attempt_envelope_id",
        "jobs_dispatch_attempt",
        ["envelope_id"],
    )

    op.create_table(
        "jobs_dispatch_receipt",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_local_run_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_arrival", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("launch_pid", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("receipt_id"),
        sa.UniqueConstraint(
            "client_id", "client_local_run_id",
            name="uq_jobs_dispatch_receipt_client_local_run",
        ),
    )
    op.create_index(
        "ix_jobs_dispatch_receipt_run_id",
        "jobs_dispatch_receipt",
        ["run_id"],
    )
    op.create_index(
        "ix_jobs_dispatch_receipt_attempt_id",
        "jobs_dispatch_receipt",
        ["attempt_id"],
    )
    op.create_index(
        "ix_jobs_dispatch_receipt_envelope_id",
        "jobs_dispatch_receipt",
        ["envelope_id"],
    )
    return


def downgrade():
    """
        Drop the dispatch + receipt tables and the shared enum.
    """
    op.drop_index("ix_jobs_dispatch_receipt_envelope_id", table_name="jobs_dispatch_receipt")
    op.drop_index("ix_jobs_dispatch_receipt_attempt_id", table_name="jobs_dispatch_receipt")
    op.drop_index("ix_jobs_dispatch_receipt_run_id", table_name="jobs_dispatch_receipt")
    op.drop_table("jobs_dispatch_receipt")

    op.drop_index("ix_jobs_dispatch_attempt_envelope_id", table_name="jobs_dispatch_attempt")
    op.drop_index("ix_jobs_dispatch_attempt_status", table_name="jobs_dispatch_attempt")
    op.drop_index("ix_jobs_dispatch_attempt_client_id", table_name="jobs_dispatch_attempt")
    op.drop_index("ix_jobs_dispatch_attempt_run_id", table_name="jobs_dispatch_attempt")
    op.drop_table("jobs_dispatch_attempt")

    sa.Enum(name=DISPATCH_ATTEMPT_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    return
