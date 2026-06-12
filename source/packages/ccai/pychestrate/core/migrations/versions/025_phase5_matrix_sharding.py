"""
Add Phase-5 / 6-matrix-sharding M1 tables.

Revision ID: 025_phase5_matrix_sharding
Revises: 024_phase4_lease_health_usage
Create Date: 2026-04-25

Adds:

- ``orch_shard_set`` (6-matrix-sharding M1 — wrapper row).
- ``orch_shard_spec`` (6-matrix-sharding M1 — composite PK on
  ``(shard_set_id, shard_id)``).

Plus the ``orch_shard_set_state`` and ``orch_shard_state``
enums.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "025_phase5_matrix_sharding"
down_revision = "024_phase4_lease_health_usage"
branch_labels = None
depends_on = None


SHARD_SET_STATE_ENUM = "orch_shard_set_state"
SHARD_SET_STATE_VALUES = (
    "EXPANDING",
    "IN_PROGRESS",
    "COMPLETED",
    "COMPLETED_PARTIAL",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
)

SHARD_STATE_ENUM = "orch_shard_state"
SHARD_STATE_VALUES = (
    "PENDING",
    "DISPATCHED",
    "RUNNING",
    "PASSED",
    "FAILED",
    "CANCELLED",
    "UNKNOWN",
)


def upgrade():
    """
        Create the shard-set + shard-spec tables.
    """
    op.create_table(
        "orch_shard_set",
        sa.Column("shard_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_kind", sa.VARCHAR(32), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_name", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "matrix_spec_canonical_sha256",
            sa.VARCHAR(64),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(*SHARD_SET_STATE_VALUES, name=SHARD_SET_STATE_ENUM),
            nullable=False,
            server_default="EXPANDING",
        ),
        sa.Column("fail_fast", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "allow_partial_success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "min_success_fraction",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("shard_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("shard_set_id"),
    )
    op.create_index(
        "ix_orch_shard_set_project",
        "orch_shard_set",
        ["project_id"],
    )
    op.create_index(
        "ix_orch_shard_set_parent",
        "orch_shard_set",
        ["parent_kind", "parent_id"],
    )

    op.create_table(
        "orch_shard_spec",
        sa.Column("shard_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shard_id", sa.VARCHAR(16), nullable=False),
        sa.Column(
            "parallel_group",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "sequence_in_group",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("dimension_values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "canonical_dims_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "state",
            sa.Enum(*SHARD_STATE_VALUES, name=SHARD_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "shard_set_id", "shard_id",
            name="pk_orch_shard_spec",
        ),
        sa.ForeignKeyConstraint(
            ["shard_set_id"],
            ["orch_shard_set.shard_set_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_orch_shard_spec_set_group_seq",
        "orch_shard_spec",
        ["shard_set_id", "parallel_group", "sequence_in_group"],
    )
    op.create_index(
        "ix_orch_shard_spec_run",
        "orch_shard_spec",
        ["run_id"],
    )
    return


def downgrade():
    """
        Drop the shard-spec + shard-set tables and the new
        enums.
    """
    op.drop_index(
        "ix_orch_shard_spec_run", table_name="orch_shard_spec",
    )
    op.drop_index(
        "ix_orch_shard_spec_set_group_seq", table_name="orch_shard_spec",
    )
    op.drop_table("orch_shard_spec")

    op.drop_index(
        "ix_orch_shard_set_parent", table_name="orch_shard_set",
    )
    op.drop_index(
        "ix_orch_shard_set_project", table_name="orch_shard_set",
    )
    op.drop_table("orch_shard_set")

    sa.Enum(name=SHARD_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=SHARD_SET_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
