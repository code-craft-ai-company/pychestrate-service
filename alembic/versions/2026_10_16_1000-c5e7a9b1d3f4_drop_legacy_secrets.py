"""secrets: drop the legacy secrets, secret_scopes, secret_versions and scope_permissions tables

Nothing in the product reads the legacy store (``specs/model-convergence.md`` sections 9 and 10): repositories, webhooks and notification channels use the vault (``phase1_secrets``),
and the pages that wrote the legacy tables are gone. This drops them.

It refuses to destroy a secret somebody could still want. If any legacy secret is live (not soft-deleted), the upgrade stops before changing anything and says what to do: deploy the previous
release, open Admin, Secrets (legacy), choose *Import N secrets into the vault*, then upgrade again. Soft-deleted secrets, their versions, empty scopes and scope grants are dropped: nothing can read them.
The staging database held 12 soft-deleted test secrets, 18 scopes and no live secret or grant when this was written (every row listed 2026-10-16).

The downgrade recreates the four tables empty, so the previous release starts; the data is not restored (take it from the pre-deploy backup).

Revision ID: c5e7a9b1d3f4
Revises: b4d6f8a0c2e5
Create Date: 2026-10-16 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "c5e7a9b1d3f4"
down_revision: Union[str, Sequence[str], None] = "b4d6f8a0c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Children first, so no table is dropped while another still points at it.
_DROP_ORDER = ("scope_permissions", "secret_versions", "secrets", "secret_scopes")


def _refuse_while_live_secrets_exist(connection: sa.engine.Connection, inspector: sa.engine.reflection.Inspector) -> None:
    """
        Stop the upgrade, before anything is changed, when a legacy secret is still live.
    """
    if inspector.has_table("secrets") is False:
        return
    live = connection.execute(sa.text("SELECT count(*) FROM secrets WHERE secret_is_deleted = :deleted"), {"deleted": False}).scalar() or 0
    if live > 0:
        raise RuntimeError(
            "Cannot drop the legacy secrets store: {} live secret(s) in it would be lost. Deploy the previous release, open Admin, Secrets (legacy), "
            "choose 'Import {} secrets into the vault', then upgrade again. (Nothing was changed.)".format(live, live)
        )
    return


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    _refuse_while_live_secrets_exist(connection, inspector)
    for table in _DROP_ORDER:
        if inspector.has_table(table):
            for index in inspector.get_indexes(table):
                op.drop_index(index["name"], table_name=table)
            op.drop_table(table)
    return


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("secret_scopes") is False:
        op.create_table(
            "secret_scopes",
            sa.Column("scope_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), autoincrement=True, nullable=False),
            sa.Column("scope_name", sa.VARCHAR(length=128), nullable=False),
            sa.Column("scope_description", sa.VARCHAR(length=512), nullable=True),
            sa.Column("scope_is_system", sa.Boolean(), nullable=False),
            sa.Column("scope_created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scope_created_by_id", sqlalchemy_utils.types.uuid.UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(["scope_created_by_id"], ["user.user_id"], name="fk_secret_scopes_scope_created_by_id"),
            sa.PrimaryKeyConstraint("scope_id"),
        )
        op.create_index(op.f("ix_secret_scopes_scope_name"), "secret_scopes", ["scope_name"], unique=True)
    if inspector.has_table("secrets") is False:
        op.create_table(
            "secrets",
            sa.Column("secret_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), autoincrement=True, nullable=False),
            sa.Column("secret_name", sa.VARCHAR(length=128), nullable=False),
            sa.Column("secret_scope_id", sa.BigInteger(), nullable=False),
            sa.Column("secret_encrypted_value", sa.LargeBinary(), nullable=False),
            sa.Column("secret_type", sa.VARCHAR(length=32), nullable=False),
            sa.Column("secret_description", sa.VARCHAR(length=512), nullable=True),
            sa.Column("secret_version", sa.Integer(), nullable=False),
            sa.Column("secret_is_deleted", sa.Boolean(), nullable=False),
            sa.Column("secret_created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("secret_updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("secret_updated_by_id", sqlalchemy_utils.types.uuid.UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(["secret_scope_id"], ["secret_scopes.scope_id"], name="fk_secrets_secret_scope_id"),
            sa.ForeignKeyConstraint(["secret_updated_by_id"], ["user.user_id"], name="fk_secrets_secret_updated_by_id"),
            sa.PrimaryKeyConstraint("secret_id"),
        )
        op.create_index("ix_secrets_scope_name", "secrets", ["secret_scope_id", "secret_name"], unique=True)
        op.create_index(op.f("ix_secrets_secret_name"), "secrets", ["secret_name"], unique=False)
        op.create_index(op.f("ix_secrets_secret_scope_id"), "secrets", ["secret_scope_id"], unique=False)
    if inspector.has_table("secret_versions") is False:
        op.create_table(
            "secret_versions",
            sa.Column("secver_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), autoincrement=True, nullable=False),
            sa.Column("secver_secret_id", sa.BigInteger(), nullable=False),
            sa.Column("secver_version", sa.Integer(), nullable=False),
            sa.Column("secver_changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("secver_changed_by_id", sqlalchemy_utils.types.uuid.UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(["secver_changed_by_id"], ["user.user_id"], name="fk_secret_versions_secver_changed_by_id"),
            sa.ForeignKeyConstraint(["secver_secret_id"], ["secrets.secret_id"], name="fk_secret_versions_secver_secret_id"),
            sa.PrimaryKeyConstraint("secver_id"),
        )
        op.create_index(op.f("ix_secret_versions_secver_secret_id"), "secret_versions", ["secver_secret_id"], unique=False)
    if inspector.has_table("scope_permissions") is False:
        op.create_table(
            "scope_permissions",
            sa.Column("scope_id", sa.BigInteger(), nullable=False),
            sa.Column("role_id", sa.BigInteger(), nullable=False),
            sa.Column("can_read", sa.Boolean(), nullable=False),
            sa.Column("can_manage", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["role_id"], ["system_roles.role_id"], name="fk_scope_permissions_role_id"),
            sa.ForeignKeyConstraint(["scope_id"], ["secret_scopes.scope_id"], name="fk_scope_permissions_scope_id"),
            sa.PrimaryKeyConstraint("scope_id", "role_id"),
        )
    return
