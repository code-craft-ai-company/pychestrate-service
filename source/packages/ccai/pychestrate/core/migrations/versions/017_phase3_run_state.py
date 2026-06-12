"""
Add Phase 3 / Layer-5 run state machine tables AND merge the
``015_phase2_enrollment_m2`` + ``016_phase3_job_envelope`` heads.

Revision ID: 017_phase3_run_state
Revises: ("015_phase2_enrollment_m2", "016_phase3_job_envelope")
Create Date: 2026-04-24

Adds:

- ``runs_run`` — authoritative run row written only by the state
  machine.
- ``runs_run_state_audit`` — append-only audit log of every
  transition.
- ``runs_run_event_outbox`` — durable outbox for milestone bus events,
  drained by :mod:`jobs.run.state.outbox_publisher`.

Chain note: this revision is both a new migration AND a merge of the
two heads that landed on ``main`` before this PR. The Phase-3-M1
sequence (PR #5 ``015_phase2_enrollment_m2``, PR #6
``016_phase3_job_envelope``) both landed with ``down_revision =
014_phase3_layer3_m2``, forking the chain. ``017`` merges both
forks and advances the head.

Operational consequence: ``alembic upgrade head`` from any ancestor
at or before ``014`` walks through ``015`` and ``016`` in
indeterminate order (both are parallel DDL-only migrations with no
conflicting table names) and then applies ``017``.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "017_phase3_run_state"
down_revision = ("015_phase2_enrollment_m2", "016_phase3_job_envelope")
branch_labels = None
depends_on = None


RUN_STATE_ENUM = "runs_run_state"
RUN_EVENT_ENUM = "runs_run_event"
TERMINAL_OUTCOME_ENUM = "runs_terminal_outcome"


RUN_STATES = (
    "PENDING",
    "DISPATCHING",
    "DISPATCHED",
    "DISPATCH_UNCONFIRMED",
    "DISPATCH_LOST",
    "DISPATCH_FAILED",
    "RUNNING",
    "PROGRESS_STALLED",
    "CANCEL_REQUESTED",
    "CANCELLING",
    "CANCELLED",
    "COMPLETING",
    "COMPLETED",
    "FAILED",
    "NEEDS_INVESTIGATION",
)


RUN_EVENTS = (
    "DISPATCH_STARTED",
    "ENVELOPE_SIGNED",
    "RECEIPT_RECORDED",
    "RECEIPT_ACK_TIMEOUT",
    "RECEIPT_LOST",
    "DISPATCH_ABORTED",
    "FIRST_PROGRESS",
    "PROGRESS_OBSERVED",
    "PROGRESS_STALL_DETECTED",
    "PROGRESS_RESUMED",
    "CANCEL_REQUESTED",
    "CANCEL_ACK_RECEIVED",
    "CANCEL_COMPLETED",
    "COMPLETION_OBSERVED",
    "FAILURE_OBSERVED",
    "RECONCILED_TO_TERMINAL",
    "INVESTIGATION_REQUIRED",
)


TERMINAL_OUTCOMES = (
    "SUCCESS",
    "FAILURE",
    "CANCELLED",
    "DISPATCH_FAILED",
    "DISPATCH_LOST",
)


def upgrade():
    """
        Create the three run-state tables plus enum types.
    """
    op.create_table(
        "runs_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.Enum(*RUN_STATES, name=RUN_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "prior_state",
            sa.Enum(*RUN_STATES, name=RUN_STATE_ENUM),
            nullable=True,
        ),
        sa.Column(
            "entered_state_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("progress_last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "terminal_outcome",
            sa.Enum(*TERMINAL_OUTCOMES, name=TERMINAL_OUTCOME_ENUM),
            nullable=True,
        ),
        sa.Column("cancel_reason", sa.VARCHAR(512), nullable=True),
        sa.Column("cancel_actor", sa.VARCHAR(256), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_runs_run_project_state", "runs_run", ["project_id", "state"])
    op.create_index(
        "ix_runs_run_state_progress",
        "runs_run",
        ["state", "progress_last_observed_at"],
    )

    op.create_table(
        "runs_run_state_audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "from_state",
            sa.Enum(*RUN_STATES, name=RUN_STATE_ENUM),
            nullable=False,
        ),
        sa.Column(
            "to_state",
            sa.Enum(*RUN_STATES, name=RUN_STATE_ENUM),
            nullable=False,
        ),
        sa.Column(
            "event",
            sa.Enum(*RUN_EVENTS, name=RUN_EVENT_ENUM),
            nullable=False,
        ),
        sa.Column("actor", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "transitioned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("audit_id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs_run.run_id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_runs_run_state_audit_run_id",
        "runs_run_state_audit",
        ["run_id"],
    )
    op.create_index(
        "ix_runs_run_state_audit_transitioned_at",
        "runs_run_state_audit",
        ["transitioned_at"],
    )

    op.create_table(
        "runs_run_event_outbox",
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.VARCHAR(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("outbox_id"),
    )
    op.create_index(
        "ix_runs_run_event_outbox_run_id",
        "runs_run_event_outbox",
        ["run_id"],
    )
    op.create_index(
        "ix_runs_run_event_outbox_published_at",
        "runs_run_event_outbox",
        ["published_at"],
    )
    return


def downgrade():
    """
        Drop the three run-state tables + enum types in reverse
        order.
    """
    op.drop_index("ix_runs_run_event_outbox_published_at", table_name="runs_run_event_outbox")
    op.drop_index("ix_runs_run_event_outbox_run_id", table_name="runs_run_event_outbox")
    op.drop_table("runs_run_event_outbox")

    op.drop_index("ix_runs_run_state_audit_transitioned_at", table_name="runs_run_state_audit")
    op.drop_index("ix_runs_run_state_audit_run_id", table_name="runs_run_state_audit")
    op.drop_table("runs_run_state_audit")

    op.drop_index("ix_runs_run_state_progress", table_name="runs_run")
    op.drop_index("ix_runs_run_project_state", table_name="runs_run")
    op.drop_table("runs_run")

    sa.Enum(name=TERMINAL_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RUN_EVENT_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RUN_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
