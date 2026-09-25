"""add delivered_at to dispatch attempts

Adds ``jobs_dispatch_attempt.delivered_at``: when a pod's long-poll
claimed the attempt. The long-poll route now delivers dispatches from
the attempt rows (any worker can serve any pod) instead of from one
process's memory, and claims an attempt by stamping this column, so a
dispatch is handed out once -- and again only if the pod has not acked
it within the ack deadline (E2E-17, E2E-16).

Purely additive (nullable column) so ``alembic upgrade head`` is
non-destructive.

Revision ID: 7d3e9a1c4b52
Revises: 4510aeb4f387
Create Date: 2026-09-25 11:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d3e9a1c4b52"
down_revision: Union[str, Sequence[str], None] = "4510aeb4f387"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Add the nullable ``delivered_at`` column.
    """
    with op.batch_alter_table("jobs_dispatch_attempt") as batch_op:
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    return


def downgrade() -> None:
    """
        Drop ``delivered_at``.
    """
    with op.batch_alter_table("jobs_dispatch_attempt") as batch_op:
        batch_op.drop_column("delivered_at")
    return
