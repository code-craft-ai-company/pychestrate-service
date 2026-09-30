"""add identity users anonymised_at

Adds ``identity_users.anonymised_at``: set when a user was anonymised in answer to a
data-protection request (the row stays, with nothing in it that names a person, so audit
records that reference the ``user_id`` keep resolving). ``NULL`` for every other user.

Purely additive (a nullable column) so ``alembic upgrade head`` is non-destructive.

Revision ID: e3b9c6d1f472
Revises: d8e1f4a7b203
Create Date: 2026-09-30 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3b9c6d1f472"
down_revision: Union[str, Sequence[str], None] = "d8e1f4a7b203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Add the nullable ``anonymised_at`` column.
    """
    with op.batch_alter_table("identity_users") as batch:
        batch.add_column(sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True))
    return


def downgrade() -> None:
    """
        Drop the ``anonymised_at`` column.
    """
    with op.batch_alter_table("identity_users") as batch:
        batch.drop_column("anonymised_at")
    return
