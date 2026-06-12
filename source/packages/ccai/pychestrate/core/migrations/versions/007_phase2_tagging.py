"""
Create Phase 2 tag assignment table (2-tagging M1).

Revision ID: 007_phase2_tagging
Revises: 006_phase2_projects
Create Date: 2026-04-20
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007_phase2_tagging"
down_revision = "006_phase2_projects"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the tagging_tag_assignments table.
    """
    op.create_table(
        "tagging_tag_assignments",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_kind", sa.VARCHAR(32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_name", sa.VARCHAR(32), nullable=False),
        sa.Column("canonical_value", sa.VARCHAR(256), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("assignment_id"),
        sa.UniqueConstraint(
            "entity_kind", "entity_id", "taxonomy_name", "canonical_value",
            name="uq_tagging_assignment_scope",
        ),
    )
    op.create_index("ix_tagging_assignment_entity", "tagging_tag_assignments", ["entity_kind", "entity_id"])
    op.create_index("ix_tagging_assignment_taxonomy", "tagging_tag_assignments", ["taxonomy_name", "canonical_value"])

    return


def downgrade():
    """
        Drop the tagging_tag_assignments table.
    """
    op.drop_index("ix_tagging_assignment_taxonomy", table_name="tagging_tag_assignments")
    op.drop_index("ix_tagging_assignment_entity", table_name="tagging_tag_assignments")
    op.drop_table("tagging_tag_assignments")

    return
