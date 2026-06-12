"""
Create Phase 2 variable bindings table (2-global-variables M1).

Revision ID: 008_phase2_global_variables
Revises: 007_phase2_tagging
Create Date: 2026-04-20
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_phase2_global_variables"
down_revision = "007_phase2_tagging"
branch_labels = None
depends_on = None


VARIABLE_SCOPE_ENUM = "variables_variable_scope"
VALUE_TYPE_ENUM = "variables_value_type"


def upgrade():
    """
        Create the variables_variable_bindings table.
    """
    op.create_table(
        "variables_variable_bindings",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("SYSTEM", "PROJECT", "PIPELINE", "JOB", name=VARIABLE_SCOPE_ENUM),
            nullable=False,
        ),
        sa.Column("scope_id", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "value_type",
            sa.Enum(
                "STRING", "INTEGER", "FLOAT", "BOOLEAN", "JSON", "SECRET_REF",
                name=VALUE_TYPE_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("set_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.UniqueConstraint(
            "scope", "scope_id", "name",
            name="uq_variables_scope_name",
        ),
    )
    op.create_index("ix_variables_scope", "variables_variable_bindings", ["scope"])
    op.create_index(
        "ix_variables_scope_scope_id",
        "variables_variable_bindings",
        ["scope", "scope_id"],
    )

    return


def downgrade():
    """
        Drop the variables_variable_bindings table.
    """
    op.drop_index("ix_variables_scope_scope_id", table_name="variables_variable_bindings")
    op.drop_index("ix_variables_scope", table_name="variables_variable_bindings")
    op.drop_table("variables_variable_bindings")

    bind = op.get_bind()
    sa.Enum(name=VALUE_TYPE_ENUM).drop(bind, checkfirst=True)
    sa.Enum(name=VARIABLE_SCOPE_ENUM).drop(bind, checkfirst=True)

    return
