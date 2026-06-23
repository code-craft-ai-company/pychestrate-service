"""
Add Phase-10 / 0-maintenance-mode + 8-webhooks-out M1 tables.

Revision ID: 038_phase10_maintenance_webhooks_out
Revises: 037_phase9_slo_views
Create Date: 2026-04-25

Adds:

- ``maintenance_mode`` (PK on scope).
- ``maintenance_mode_audit``.
- ``webhooks_out_target``.
- ``webhooks_out_delivery``.

Plus the ``webhook_out_delivery_outcome`` and
``webhook_out_signature_scheme`` enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038_phase10_maintenance_webhooks_out"
down_revision = "037_phase9_slo_views"
branch_labels = None
depends_on = None


WEBHOOK_DELIVERY_OUTCOME_ENUM = "webhook_out_delivery_outcome"
WEBHOOK_DELIVERY_OUTCOME_VALUES = (
    "PENDING", "SUCCEEDED", "FAILED", "REJECTED_DISABLED",
)

WEBHOOK_SIGNATURE_SCHEME_ENUM = "webhook_out_signature_scheme"
WEBHOOK_SIGNATURE_SCHEME_VALUES = ("HMAC_SHA256",)


def upgrade():
    """
        Create the maintenance + webhooks-out tables.
    """
    op.create_table(
        "maintenance_mode",
        sa.Column("scope", sa.VARCHAR(160), nullable=False),
        sa.Column(
            "mode", sa.VARCHAR(16), nullable=False, server_default="active",
        ),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("scope"),
    )

    op.create_table(
        "maintenance_mode_audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.VARCHAR(160), nullable=False),
        sa.Column("from_mode", sa.VARCHAR(16), nullable=False),
        sa.Column("to_mode", sa.VARCHAR(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "ix_maintenance_mode_audit_scope_changed",
        "maintenance_mode_audit",
        ["scope", "changed_at"],
    )

    op.create_table(
        "webhooks_out_target",
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "secret_ref", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "signature_scheme",
            sa.Enum(
                *WEBHOOK_SIGNATURE_SCHEME_VALUES,
                name=WEBHOOK_SIGNATURE_SCHEME_ENUM,
            ),
            nullable=False,
            server_default="HMAC_SHA256",
        ),
        sa.Column(
            "topic_filters", sa.JSON(), nullable=False, server_default="[]",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "custom_headers", sa.JSON(), nullable=False, server_default="{}",
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("target_id"),
        sa.UniqueConstraint(
            "project_id", "name",
            name="uq_webhooks_out_target_project_name",
        ),
    )
    op.create_index(
        "ix_webhooks_out_target_project_enabled",
        "webhooks_out_target",
        ["project_id", "enabled"],
    )

    op.create_table(
        "webhooks_out_delivery",
        sa.Column(
            "delivery_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column(
            "payload_digest_sha256",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("signature", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "request_headers", sa.JSON(), nullable=False, server_default="{}",
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                *WEBHOOK_DELIVERY_OUTCOME_VALUES,
                name=WEBHOOK_DELIVERY_OUTCOME_ENUM,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("delivery_id"),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["webhooks_out_target.target_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_webhooks_out_delivery_target_attempted",
        "webhooks_out_delivery",
        ["target_id", "attempted_at"],
    )
    op.create_index(
        "ix_webhooks_out_delivery_outcome",
        "webhooks_out_delivery",
        ["outcome"],
    )
    return


def downgrade():
    """
        Drop the maintenance + webhooks-out tables.
    """
    op.drop_index(
        "ix_webhooks_out_delivery_outcome",
        table_name="webhooks_out_delivery",
    )
    op.drop_index(
        "ix_webhooks_out_delivery_target_attempted",
        table_name="webhooks_out_delivery",
    )
    op.drop_table("webhooks_out_delivery")

    op.drop_index(
        "ix_webhooks_out_target_project_enabled",
        table_name="webhooks_out_target",
    )
    op.drop_table("webhooks_out_target")

    op.drop_index(
        "ix_maintenance_mode_audit_scope_changed",
        table_name="maintenance_mode_audit",
    )
    op.drop_table("maintenance_mode_audit")
    op.drop_table("maintenance_mode")

    sa.Enum(name=WEBHOOK_SIGNATURE_SCHEME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=WEBHOOK_DELIVERY_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    return
