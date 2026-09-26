"""pod names are unique only among clients that are not revoked

Replaces the ``uq_clients_clients_project_pod`` unique constraint on
``clients_clients (project_id, pod_name)`` with the partial unique
index ``uq_clients_clients_project_pod_unrevoked``. A revoked client
used to keep its pod name forever, so the replacement for a broken lab
machine could not enroll under it: redeem answered 409 (E2E-25).
Revoked rows stay, so run history still resolves the client.

Revision ID: 9b4e2f7a1c63
Revises: 7d3e9a1c4b52
Create Date: 2026-09-26 11:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b4e2f7a1c63"
down_revision: Union[str, Sequence[str], None] = "7d3e9a1c4b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UNREVOKED_PREDICATE = "status != 'REVOKED'"


def upgrade() -> None:
    """
        Drop the table-wide constraint; add the partial unique index.
    """
    with op.batch_alter_table("clients_clients") as batch_op:
        batch_op.drop_constraint("uq_clients_clients_project_pod", type_="unique")
    op.create_index(
        "uq_clients_clients_project_pod_unrevoked",
        "clients_clients",
        ["project_id", "pod_name"],
        unique=True,
        sqlite_where=sa.text(UNREVOKED_PREDICATE),
        postgresql_where=sa.text(UNREVOKED_PREDICATE),
    )
    return


def downgrade() -> None:
    """
        Restore the table-wide constraint. Fails if a revoked client
        and its replacement share a pod name.
    """
    op.drop_index("uq_clients_clients_project_pod_unrevoked", table_name="clients_clients")
    with op.batch_alter_table("clients_clients") as batch_op:
        batch_op.create_unique_constraint(
            "uq_clients_clients_project_pod", ["project_id", "pod_name"],
        )
    return
