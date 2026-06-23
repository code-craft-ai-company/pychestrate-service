"""
Add Phase 4 / Layer-4 inventory + pool tables.

Revision ID: 022_phase4_resource_inventory_pools
Revises: 021_phase3_b4_artifact_cancel_offline
Create Date: 2026-04-24

Adds:

- ``resources_resource`` (4-resource-inventory)
- ``resources_resource_pool`` (4-resource-pools)
- ``resources_resource_pool_member`` (4-resource-pools)

Plus the ``resources_resource_state`` enum.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "022_phase4_resource_inventory_pools"
down_revision = "021_phase3_b4_artifact_cancel_offline"
branch_labels = None
depends_on = None


RESOURCE_STATE_ENUM = "resources_resource_state"
RESOURCE_STATE_VALUES = ("AVAILABLE", "LEASED", "QUARANTINED", "MAINTENANCE", "RETIRED")


def upgrade():
    """
        Create the inventory + pool tables.
    """
    op.create_table(
        "resources_resource",
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("display_name", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("identity_hash", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.Enum(*RESOURCE_STATE_VALUES, name=RESOURCE_STATE_ENUM),
            nullable=False,
            server_default="AVAILABLE",
        ),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.PrimaryKeyConstraint("resource_id"),
    )
    op.create_index("ix_resources_resource_kind_state", "resources_resource", ["kind", "state"])
    op.create_index("ix_resources_resource_project", "resources_resource", ["project_id"])
    op.create_index(
        "ix_resources_resource_identity",
        "resources_resource",
        ["kind", "identity_hash"],
    )

    op.create_table(
        "resources_resource_pool",
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column("description", sa.VARCHAR(1024), nullable=False, server_default=""),
        sa.Column("capability_tags", sa.JSON(), nullable=False, server_default="[]"),
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
        sa.PrimaryKeyConstraint("pool_id"),
        sa.UniqueConstraint(
            "project_id", "name",
            name="uq_resources_resource_pool_project_name",
        ),
    )
    op.create_index(
        "ix_resources_resource_pool_project",
        "resources_resource_pool",
        ["project_id"],
    )

    op.create_table(
        "resources_resource_pool_member",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("membership_id"),
        sa.ForeignKeyConstraint(
            ["pool_id"], ["resources_resource_pool.pool_id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "pool_id", "resource_id",
            name="uq_resources_resource_pool_member_pool_resource",
        ),
    )
    op.create_index(
        "ix_resources_resource_pool_member_resource",
        "resources_resource_pool_member",
        ["resource_id"],
    )
    return


def downgrade():
    """
        Drop the inventory + pool tables and the resource state
        enum.
    """
    op.drop_index(
        "ix_resources_resource_pool_member_resource",
        table_name="resources_resource_pool_member",
    )
    op.drop_table("resources_resource_pool_member")

    op.drop_index(
        "ix_resources_resource_pool_project",
        table_name="resources_resource_pool",
    )
    op.drop_table("resources_resource_pool")

    op.drop_index("ix_resources_resource_identity", table_name="resources_resource")
    op.drop_index("ix_resources_resource_project", table_name="resources_resource")
    op.drop_index("ix_resources_resource_kind_state", table_name="resources_resource")
    op.drop_table("resources_resource")

    sa.Enum(name=RESOURCE_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    return
