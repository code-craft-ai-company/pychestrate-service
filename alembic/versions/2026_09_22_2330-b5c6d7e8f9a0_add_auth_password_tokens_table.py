"""add auth password tokens table

Adds ``auth_password_tokens``: single-use invite and password-reset
links (only the SHA-256 digest of the link secret is stored) behind
the admin "Reset password" / "Invite" actions and the /password/set
redemption page.

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-09-22 23:30:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``auth_password_tokens`` table.
    """
    op.create_table(
        "auth_password_tokens",
        sa.Column("token_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum("INVITE", "RESET", name="auth_password_token_purpose"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity_users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_auth_password_tokens_user",
        "auth_password_tokens",
        ["user_id"],
        unique=False,
    )
    return


def downgrade() -> None:
    """
        Drop the ``auth_password_tokens`` table and its enum type.
    """
    op.drop_index("ix_auth_password_tokens_user", table_name="auth_password_tokens")
    op.drop_table("auth_password_tokens")
    sa.Enum(name="auth_password_token_purpose").drop(op.get_bind(), checkfirst=True)
    return
