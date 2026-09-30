"""add ui form drafts table

Adds ``ui_form_drafts``: what a person had typed into a form when their sign-in
or its anti-forgery token expired, kept for a few minutes so the form can be
filled in again after they sign back in (XC-11). Only the SHA-256 digest of the
draft's token is stored; a draft is read once and deleted.

Purely additive so ``alembic upgrade head`` is non-destructive.

Revision ID: d8e1f4a7b203
Revises: c5a7d2e91b48
Create Date: 2026-09-29 22:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = "d8e1f4a7b203"
down_revision: Union[str, Sequence[str], None] = "c5a7d2e91b48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
        Create the ``ui_form_drafts`` table.
    """
    op.create_table(
        "ui_form_drafts",
        sa.Column("draft_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("draft_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_ui_form_drafts_expires", "ui_form_drafts", ["expires_at"], unique=False)
    return


def downgrade() -> None:
    """
        Drop the ``ui_form_drafts`` table.
    """
    op.drop_index("ix_ui_form_drafts_expires", table_name="ui_form_drafts")
    op.drop_table("ui_form_drafts")
    return
