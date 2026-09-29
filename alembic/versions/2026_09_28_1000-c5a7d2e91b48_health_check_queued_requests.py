"""a person's health check can be queued, and the last outcome keeps its reason

Adds two columns to ``health_check_configs``:

* ``hcc_check_requested_at``: when a person asked for a check to run now.
  The housekeeping worker runs requested checks ahead of the scheduled
  ones and clears the column, so "Run Health Check" no longer probes the
  device inside the web request (RES-39).
* ``hcc_last_check_message``: why the last check failed or was not run,
  so the health page can say so after the request that started it has
  gone.

Revision ID: c5a7d2e91b48
Revises: 9b4e2f7a1c63
Create Date: 2026-09-28 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5a7d2e91b48"
down_revision: Union[str, Sequence[str], None] = "9b4e2f7a1c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "health_check_configs"


def upgrade() -> None:
    """
        Add the two nullable columns.
    """
    op.add_column(TABLE, sa.Column("hcc_check_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("hcc_last_check_message", sa.VARCHAR(512), nullable=True))
    return


def downgrade() -> None:
    """
        Drop them again.
    """
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_column("hcc_last_check_message")
        batch_op.drop_column("hcc_check_requested_at")
    return
