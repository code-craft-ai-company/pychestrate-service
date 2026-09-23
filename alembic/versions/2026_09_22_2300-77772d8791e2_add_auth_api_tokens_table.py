"""add auth api tokens table

Adds ``auth_api_tokens`` for machine identity (audit finding
ORG-F02): personal access tokens and service-account tokens sent as
``Authorization: Bearer pyc_...``. Only the SHA-256 digest of each
token is stored. Service accounts need no table of their own: they
are ``identity_users`` rows with
``provisioning_source = 'service_account'``.

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: 77772d8791e2
Revises: a3b4c5d6e7f8
Create Date: 2026-09-22 23:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "77772d8791e2"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``auth_api_tokens`` table and its user index.
    """
    op.create_table(
        "auth_api_tokens",
        sa.Column("token_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["identity_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["identity_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("token_sha256", name="uq_auth_api_tokens_token_sha256"),
    )
    op.create_index("ix_auth_api_tokens_user_id", "auth_api_tokens", ["user_id"], unique=False)
    return


def downgrade() -> None:
    """
        Drop the ``auth_api_tokens`` table. Every issued API token
        stops working.
    """
    op.drop_index("ix_auth_api_tokens_user_id", table_name="auth_api_tokens")
    op.drop_table("auth_api_tokens")
    return
