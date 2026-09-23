"""add project repository refs table

Adds ``project_repository_refs``: the branches and tags of each project
repository as last seen by a fetch. A fetch compares what the remote
reports with these rows to find new commits, branches and tags, and
fires the project's repository watches for them (PRJ-10).

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: 4510aeb4f387
Revises: a6ad11324568
Create Date: 2026-09-23 11:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4510aeb4f387"
down_revision: Union[str, Sequence[str], None] = "a6ad11324568"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``project_repository_refs`` table.
    """
    op.create_table(
        "project_repository_refs",
        sa.Column("prref_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("prepo_id", sa.BigInteger(), nullable=False),
        sa.Column("prref_kind", sa.VARCHAR(length=16), nullable=False),
        sa.Column("prref_name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("prref_commit_sha", sa.VARCHAR(length=64), nullable=False),
        sa.Column("prref_first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prref_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["prepo_id"], ["project_repositories.prepo_id"]),
        sa.PrimaryKeyConstraint("prref_id"),
        sa.UniqueConstraint(
            "prepo_id", "prref_kind", "prref_name", name="uq_project_repository_ref"
        ),
    )
    op.create_index(
        op.f("ix_project_repository_refs_prepo_id"),
        "project_repository_refs",
        ["prepo_id"],
        unique=False,
    )
    return


def downgrade() -> None:
    """
        Drop the ``project_repository_refs`` table.
    """
    op.drop_index(
        op.f("ix_project_repository_refs_prepo_id"),
        table_name="project_repository_refs",
    )
    op.drop_table("project_repository_refs")
    return
