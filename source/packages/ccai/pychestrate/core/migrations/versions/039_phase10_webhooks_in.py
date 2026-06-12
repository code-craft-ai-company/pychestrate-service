"""
Add Phase-10 / 8-webhooks-in M1 tables.

Revision ID: 039_phase10_webhooks_in
Revises: 038_phase10_maintenance_webhooks_out
Create Date: 2026-04-25

Adds:

- ``webhooks_in_configurations``.
- ``webhooks_in_seen_deliveries``.
- ``webhooks_in_deadletter_index``.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "039_phase10_webhooks_in"
down_revision = "038_phase10_maintenance_webhooks_out"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the inbound-webhook tables.
    """
    op.create_table(
        "webhooks_in_configurations",
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.VARCHAR(64), nullable=False),
        sa.Column("hook_name", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "secret_ref", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "mtls_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("webhook_id"),
        sa.UniqueConstraint(
            "project_id", "provider", "hook_name",
            name="uq_webhooks_in_configurations_project_provider_name",
        ),
    )
    op.create_index(
        "ix_webhooks_in_configurations_provider_name",
        "webhooks_in_configurations",
        ["provider", "hook_name"],
    )

    op.create_table(
        "webhooks_in_seen_deliveries",
        sa.Column("provider", sa.VARCHAR(64), nullable=False),
        sa.Column("hook_name", sa.VARCHAR(128), nullable=False),
        sa.Column("delivery_id", sa.VARCHAR(256), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", "hook_name", "delivery_id"),
    )
    op.create_index(
        "ix_webhooks_in_seen_deliveries_expires_at",
        "webhooks_in_seen_deliveries",
        ["expires_at"],
    )

    op.create_table(
        "webhooks_in_deadletter_index",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.VARCHAR(64), nullable=False),
        sa.Column("hook_name", sa.VARCHAR(128), nullable=False),
        sa.Column("object_store_path", sa.Text(), nullable=False),
        sa.Column(
            "content_type", sa.VARCHAR(128), nullable=False, server_default="",
        ),
        sa.Column(
            "byte_size", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("reason", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "recoverable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_webhooks_in_deadletter_index_provider_name",
        "webhooks_in_deadletter_index",
        ["provider", "hook_name"],
    )
    op.create_index(
        "ix_webhooks_in_deadletter_index_expires_at",
        "webhooks_in_deadletter_index",
        ["expires_at"],
    )
    return


def downgrade():
    """
        Drop the inbound-webhook tables.
    """
    op.drop_index(
        "ix_webhooks_in_deadletter_index_expires_at",
        table_name="webhooks_in_deadletter_index",
    )
    op.drop_index(
        "ix_webhooks_in_deadletter_index_provider_name",
        table_name="webhooks_in_deadletter_index",
    )
    op.drop_table("webhooks_in_deadletter_index")

    op.drop_index(
        "ix_webhooks_in_seen_deliveries_expires_at",
        table_name="webhooks_in_seen_deliveries",
    )
    op.drop_table("webhooks_in_seen_deliveries")

    op.drop_index(
        "ix_webhooks_in_configurations_provider_name",
        table_name="webhooks_in_configurations",
    )
    op.drop_table("webhooks_in_configurations")
    return
