"""
Create Phase 2 project aggregate tables (2-projects M1).

Revision ID: 006_phase2_projects
Revises: 005_phase2_clients
Create Date: 2026-04-20

Creates:

- projects_projects                     -- project aggregate root
- projects_project_member_bindings      -- user x project x role triples

M2 adds archive/delete support (no new columns, state transitions only)
and the ProjectMetadataFieldExtension registry which persists into the
existing ``extension_fields`` JSONB column.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_phase2_projects"
down_revision = "005_phase2_clients"
branch_labels = None
depends_on = None


PROJECT_STATE_ENUM = "projects_project_state"


def upgrade():
    """
        Create the 2-projects M1 tables.
    """
    op.create_table(
        "projects_projects",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.VARCHAR(63), nullable=False),
        sa.Column("display_name", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column("description", sa.VARCHAR(2048), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.Enum("ACTIVE", "ARCHIVED", name=PROJECT_STATE_ENUM),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("owning_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", sa.VARCHAR(128), nullable=True),
        sa.Column("template_version", sa.VARCHAR(32), nullable=True),
        sa.Column("extension_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("project_id"),
        sa.UniqueConstraint("slug", name="uq_projects_projects_slug"),
    )
    op.create_index("ix_projects_projects_state", "projects_projects", ["state"])
    op.create_index("ix_projects_projects_owning_group_id", "projects_projects", ["owning_group_id"])

    op.create_table(
        "projects_project_member_bindings",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects_projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_name", sa.VARCHAR(64), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.UniqueConstraint(
            "project_id", "user_id", "role_name",
            name="uq_projects_member_bindings_scope",
        ),
    )
    op.create_index("ix_projects_member_bindings_user", "projects_project_member_bindings", ["user_id"])

    return


def downgrade():
    """
        Drop 2-projects M1 tables.
    """
    op.drop_index("ix_projects_member_bindings_user", table_name="projects_project_member_bindings")
    op.drop_table("projects_project_member_bindings")

    op.drop_index("ix_projects_projects_owning_group_id", table_name="projects_projects")
    op.drop_index("ix_projects_projects_state", table_name="projects_projects")
    op.drop_table("projects_projects")

    bind = op.get_bind()
    sa.Enum(name=PROJECT_STATE_ENUM).drop(bind, checkfirst=True)

    return
