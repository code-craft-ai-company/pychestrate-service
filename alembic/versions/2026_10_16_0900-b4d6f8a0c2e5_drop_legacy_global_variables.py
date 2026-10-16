"""variables: drop the legacy global_variables and global_variable_history tables

The Admin Variables pages and the runtime read and write one store since ``f7b2c9a4d1e6`` (the SYSTEM-scope bindings of ``variables_variable_bindings``), and that migration copied the
legacy rows and their history into it earlier in this same chain, so a database that reaches this revision has been copied. Nothing reads the legacy tables any more
(``specs/model-convergence.md`` section 10); this drops them. The staging database held no rows in either when this was written (listed 2026-10-16).

The downgrade recreates both tables empty, so the previous release starts; the data is not restored (take it from the pre-deploy backup).

Revision ID: b4d6f8a0c2e5
Revises: a3c5e7f9b1d2
Create Date: 2026-10-16 09:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "b4d6f8a0c2e5"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("global_variable_history"):
        for index in inspector.get_indexes("global_variable_history"):
            op.drop_index(index["name"], table_name="global_variable_history")
        op.drop_table("global_variable_history")
    if inspector.has_table("global_variables"):
        for index in inspector.get_indexes("global_variables"):
            op.drop_index(index["name"], table_name="global_variables")
        op.drop_table("global_variables")
    return


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("global_variables") is False:
        op.create_table(
            "global_variables",
            sa.Column("gvar_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), autoincrement=True, nullable=False),
            sa.Column("gvar_name", sa.VARCHAR(length=128), nullable=False),
            sa.Column("gvar_value_json", sa.Text(), nullable=False),
            sa.Column("gvar_type", sa.VARCHAR(length=16), nullable=False),
            sa.Column("gvar_description", sa.VARCHAR(length=512), nullable=True),
            sa.Column("gvar_default_value_json", sa.Text(), nullable=True),
            sa.Column("gvar_created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("gvar_updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("gvar_updated_by_id", sqlalchemy_utils.types.uuid.UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(["gvar_updated_by_id"], ["user.user_id"], name="fk_global_variables_gvar_updated_by_id"),
            sa.PrimaryKeyConstraint("gvar_id"),
        )
        op.create_index(op.f("ix_global_variables_gvar_name"), "global_variables", ["gvar_name"], unique=True)
    if inspector.has_table("global_variable_history") is False:
        op.create_table(
            "global_variable_history",
            sa.Column("gvarhist_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), autoincrement=True, nullable=False),
            sa.Column("gvarhist_variable_id", sa.BigInteger(), nullable=False),
            sa.Column("gvarhist_variable_name", sa.VARCHAR(length=128), nullable=False),
            sa.Column("gvarhist_old_value_json", sa.Text(), nullable=True),
            sa.Column("gvarhist_new_value_json", sa.Text(), nullable=True),
            sa.Column("gvarhist_changed_by_id", sqlalchemy_utils.types.uuid.UUIDType(), nullable=True),
            sa.Column("gvarhist_changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["gvarhist_changed_by_id"], ["user.user_id"], name="fk_global_variable_history_gvarhist_changed_by_id"),
            sa.ForeignKeyConstraint(["gvarhist_variable_id"], ["global_variables.gvar_id"], name="fk_global_variable_history_gvarhist_variable_id"),
            sa.PrimaryKeyConstraint("gvarhist_id"),
        )
        op.create_index(op.f("ix_global_variable_history_gvarhist_variable_id"), "global_variable_history", ["gvarhist_variable_id"], unique=False)
    return
