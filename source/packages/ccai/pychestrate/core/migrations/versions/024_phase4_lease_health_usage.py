"""
Add Phase 4 / Layer-4 lease + resource-health + timeline tables.

Revision ID: 024_phase4_lease_health_usage
Revises: 023_phase4_checkout_conflict_scheduler
Create Date: 2026-04-24

Adds:

- ``resources_lease`` (4-lease-heartbeat M1)
- ``resources_resource_health`` (4-resource-health M1)
- ``resources_timeline_event`` (4-usage-history M1)

Plus the ``resources_lease_state``,
``resources_health_probe_outcome`` and
``resources_usage_event_type`` enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "024_phase4_lease_health_usage"
down_revision = "023_phase4_checkout_conflict_scheduler"
branch_labels = None
depends_on = None


LEASE_STATE_ENUM = "resources_lease_state"
LEASE_STATE_VALUES = ("ACTIVE", "EXPIRED", "RELEASED")

PROBE_OUTCOME_ENUM = "resources_health_probe_outcome"
PROBE_OUTCOME_VALUES = ("PASS", "FAIL", "UNKNOWN")

USAGE_EVENT_TYPE_ENUM = "resources_usage_event_type"
USAGE_EVENT_TYPE_VALUES = (
    "RESOURCE_REGISTERED",
    "RESOURCE_QUARANTINED",
    "RESOURCE_UNQUARANTINED",
    "RESOURCE_RETIRED",
    "RESERVATION_GRANTED",
    "RESERVATION_RELEASED",
    "RESERVATION_FORCED_RELEASED",
    "RESERVATION_REJECTED",
    "LEASE_ATTACHED",
    "LEASE_RENEWED",
    "LEASE_EXPIRED",
    "HEALTH_PROBED",
)


def upgrade():
    """
        Create the lease + health + timeline tables.
    """
    op.create_table(
        "resources_lease",
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "lease_kind",
            sa.VARCHAR(32),
            nullable=False,
            server_default="fixed",
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "state",
            sa.Enum(*LEASE_STATE_VALUES, name=LEASE_STATE_ENUM),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "attached_at",
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
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.VARCHAR(64), nullable=True),
        sa.Column(
            "heartbeat_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("lease_id"),
        sa.UniqueConstraint(
            "reservation_id",
            name="uq_resources_lease_reservation",
        ),
    )
    op.create_index(
        "ix_resources_lease_state_expires",
        "resources_lease",
        ["state", "expires_at"],
    )
    op.create_index(
        "ix_resources_lease_resource",
        "resources_lease",
        ["resource_id"],
    )

    op.create_table(
        "resources_resource_health",
        sa.Column("health_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "probe_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "probe_period_seconds", sa.Integer(), nullable=False, server_default="60",
        ),
        sa.Column(
            "last_outcome",
            sa.Enum(*PROBE_OUTCOME_VALUES, name=PROBE_OUTCOME_ENUM),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pass_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fail_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_probe_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("health_id"),
        sa.UniqueConstraint(
            "resource_id",
            name="uq_resources_resource_health_resource",
        ),
    )
    op.create_index(
        "ix_resources_resource_health_next_probe",
        "resources_resource_health",
        ["next_probe_at", "probe_name"],
    )
    op.create_index(
        "ix_resources_resource_health_project",
        "resources_resource_health",
        ["project_id"],
    )

    op.create_table(
        "resources_timeline_event",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(*USAGE_EVENT_TYPE_VALUES, name=USAGE_EVENT_TYPE_ENUM),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "pod_event_group_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "at_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("annotations", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "source_event_id", "resource_id",
            name="uq_resources_timeline_event_source_resource",
        ),
    )
    op.create_index(
        "ix_resources_timeline_event_resource_at",
        "resources_timeline_event",
        ["resource_id", "at_ts"],
    )
    op.create_index(
        "ix_resources_timeline_event_type_at",
        "resources_timeline_event",
        ["event_type", "at_ts"],
    )
    op.create_index(
        "ix_resources_timeline_event_pod_group",
        "resources_timeline_event",
        ["pod_event_group_id"],
    )
    return


def downgrade():
    """
        Drop the lease + health + timeline tables and the new
        enums.
    """
    op.drop_index(
        "ix_resources_timeline_event_pod_group",
        table_name="resources_timeline_event",
    )
    op.drop_index(
        "ix_resources_timeline_event_type_at",
        table_name="resources_timeline_event",
    )
    op.drop_index(
        "ix_resources_timeline_event_resource_at",
        table_name="resources_timeline_event",
    )
    op.drop_table("resources_timeline_event")

    op.drop_index(
        "ix_resources_resource_health_project",
        table_name="resources_resource_health",
    )
    op.drop_index(
        "ix_resources_resource_health_next_probe",
        table_name="resources_resource_health",
    )
    op.drop_table("resources_resource_health")

    op.drop_index(
        "ix_resources_lease_resource", table_name="resources_lease",
    )
    op.drop_index(
        "ix_resources_lease_state_expires", table_name="resources_lease",
    )
    op.drop_table("resources_lease")

    sa.Enum(name=USAGE_EVENT_TYPE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PROBE_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=LEASE_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
