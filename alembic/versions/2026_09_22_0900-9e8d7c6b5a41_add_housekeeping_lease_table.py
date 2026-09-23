"""add housekeeping lease table

Adds ``housekeeping_lease``: one row per periodic housekeeping task
(reservation activation, allocation expiry, scheduled health checks).
A server process takes a task's row before running it, so only one
process runs each task at a time; the row also records when the task
last ran and what it did.

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: 9e8d7c6b5a41
Revises: a3b4c5d6e7f8
Create Date: 2026-09-22 09:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e8d7c6b5a41"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``housekeeping_lease`` table.
    """
    op.create_table(
        "housekeeping_lease",
        sa.Column("task_name", sa.String(length=128), nullable=False),
        sa.Column("holder_id", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("task_name", name="pk_housekeeping_lease"),
    )
    return


def downgrade() -> None:
    """
        Drop the ``housekeeping_lease`` table.
    """
    op.drop_table("housekeeping_lease")
    return
