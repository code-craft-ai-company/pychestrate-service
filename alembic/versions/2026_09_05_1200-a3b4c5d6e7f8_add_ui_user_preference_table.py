"""add ui user preference table

Adds ``ui_user_preference`` introduced by ``9-ui-profiles`` M2: a
generic ``(user_id, key) -> value_json`` store whose first key,
``ui.surfaces``, holds a user's automation-surface override.

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-05 12:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``ui_user_preference`` table.
    """
    op.create_table(
        "ui_user_preference",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_ui_user_preference"),
    )
    return


def downgrade() -> None:
    """
        Drop the ``ui_user_preference`` table.
    """
    op.drop_table("ui_user_preference")
    return
