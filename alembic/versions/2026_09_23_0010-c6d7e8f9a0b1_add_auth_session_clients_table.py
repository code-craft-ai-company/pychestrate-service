"""add auth session clients table

Adds ``auth_session_clients``: where each sign-in session was opened
from -- the client's real address (resolved behind trusted proxies)
and its User-Agent -- which the admin sessions page shows. One row per
``auth_sessions`` row, deleted with it. Sessions opened before this
revision have no row ("not recorded").

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-09-23 00:10:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``auth_session_clients`` table.
    """
    op.create_table(
        "auth_session_clients",
        sa.Column("session_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("client_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["auth_sessions.session_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    return


def downgrade() -> None:
    """
        Drop the ``auth_session_clients`` table.
    """
    op.drop_table("auth_session_clients")
    return
