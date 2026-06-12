"""
Add Phase 4 / Layer-4 reservation + scheduler-entry tables.

Revision ID: 023_phase4_checkout_conflict_scheduler
Revises: 022_phase4_resource_inventory_pools
Create Date: 2026-04-24

Adds:

- ``resources_reservation`` (4-checkout-checkin)
- ``resources_scheduler_entry`` (4-reservation-scheduler M1)

Plus the ``resources_reservation_mode``,
``resources_reservation_state`` and
``resources_scheduler_entry_state`` enums.

The 4-conflict-deconfliction feature is purely in-memory at M1 —
its rules read snapshots of ``resources_reservation`` and produce
``RuleDecision`` objects for the checkout service. No new tables.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "023_phase4_checkout_conflict_scheduler"
down_revision = "022_phase4_resource_inventory_pools"
branch_labels = None
depends_on = None


RESERVATION_MODE_ENUM = "resources_reservation_mode"
RESERVATION_MODE_VALUES = ("EXCLUSIVE", "SHARED")

RESERVATION_STATE_ENUM = "resources_reservation_state"
RESERVATION_STATE_VALUES = (
    "PENDING", "GRANTED", "RELEASED", "REJECTED", "FORCED_RELEASED",
)

SCHEDULER_ENTRY_STATE_ENUM = "resources_scheduler_entry_state"
SCHEDULER_ENTRY_STATE_VALUES = ("QUEUED", "DISPATCHED", "CANCELLED")


def upgrade():
    """
        Create the reservation + scheduler-entry tables.
    """
    op.create_table(
        "resources_reservation",
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "mode",
            sa.Enum(*RESERVATION_MODE_VALUES, name=RESERVATION_MODE_ENUM),
            nullable=False,
            server_default="EXCLUSIVE",
        ),
        sa.Column(
            "state",
            sa.Enum(*RESERVATION_STATE_VALUES, name=RESERVATION_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("note", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("reservation_id"),
    )
    op.create_index(
        "ix_resources_reservation_resource_state",
        "resources_reservation",
        ["resource_id", "state"],
    )
    op.create_index(
        "ix_resources_reservation_project",
        "resources_reservation",
        ["project_id"],
    )
    op.create_index(
        "ix_resources_reservation_requested_by",
        "resources_reservation",
        ["requested_by"],
    )

    op.create_table(
        "resources_scheduler_entry",
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm", sa.VARCHAR(64), nullable=False, server_default="fifo"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("fair_share_key", sa.VARCHAR(128), nullable=True),
        sa.Column(
            "fair_share_weight",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "state",
            sa.Enum(*SCHEDULER_ENTRY_STATE_VALUES, name=SCHEDULER_ENTRY_STATE_ENUM),
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint(
            "reservation_id",
            name="uq_resources_scheduler_entry_reservation",
        ),
    )
    op.create_index(
        "ix_resources_scheduler_entry_pool_state_priority",
        "resources_scheduler_entry",
        ["pool_id", "state", "priority", "enqueued_at"],
    )
    op.create_index(
        "ix_resources_scheduler_entry_pool_state_deadline",
        "resources_scheduler_entry",
        ["pool_id", "state", "deadline_at"],
    )
    op.create_index(
        "ix_resources_scheduler_entry_fair_share",
        "resources_scheduler_entry",
        ["fair_share_key", "state"],
    )
    return


def downgrade():
    """
        Drop the reservation + scheduler tables and the new
        enums.
    """
    op.drop_index(
        "ix_resources_scheduler_entry_fair_share",
        table_name="resources_scheduler_entry",
    )
    op.drop_index(
        "ix_resources_scheduler_entry_pool_state_deadline",
        table_name="resources_scheduler_entry",
    )
    op.drop_index(
        "ix_resources_scheduler_entry_pool_state_priority",
        table_name="resources_scheduler_entry",
    )
    op.drop_table("resources_scheduler_entry")

    op.drop_index(
        "ix_resources_reservation_requested_by",
        table_name="resources_reservation",
    )
    op.drop_index(
        "ix_resources_reservation_project",
        table_name="resources_reservation",
    )
    op.drop_index(
        "ix_resources_reservation_resource_state",
        table_name="resources_reservation",
    )
    op.drop_table("resources_reservation")

    sa.Enum(name=SCHEDULER_ENTRY_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RESERVATION_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RESERVATION_MODE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
