"""
Add Phase-6 / 6-source-integrations M1 tables.

Revision ID: 029_phase6_source_integrations
Revises: 028_phase6_pipeline_definition
Create Date: 2026-04-25

Adds:

- ``orch_scm_project_config``.
- ``orch_scm_webhook_delivery`` (composite PK on
  ``(project_id, delivery_id)`` for dedup).
- ``orch_scm_last_seen_head`` (composite PK on
  ``(project_id, ref)``).
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "029_phase6_source_integrations"
down_revision = "028_phase6_pipeline_definition"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the source-integrations tables.
    """
    op.create_table(
        "orch_scm_project_config",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "repo_key", sa.VARCHAR(256), nullable=False, server_default="",
        ),
        sa.Column(
            "pipeline_file_path",
            sa.VARCHAR(256),
            nullable=False,
            server_default=".pychestrate/pipeline.yaml",
        ),
        sa.Column(
            "use_polling",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "polling_ref_glob",
            sa.VARCHAR(128),
            nullable=False,
            server_default="",
        ),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "orch_scm_webhook_delivery",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "provider_name", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "event_kind", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "delivery_id",
            name="pk_orch_scm_webhook_delivery",
        ),
    )
    op.create_index(
        "ix_orch_scm_webhook_delivery_received",
        "orch_scm_webhook_delivery",
        ["project_id", "received_at"],
    )

    op.create_table(
        "orch_scm_last_seen_head",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ref", sa.VARCHAR(256), nullable=False),
        sa.Column(
            "commit_sha", sa.VARCHAR(64), nullable=False, server_default="",
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "ref",
            name="pk_orch_scm_last_seen_head",
        ),
    )
    return


def downgrade():
    """
        Drop the source-integrations tables.
    """
    op.drop_table("orch_scm_last_seen_head")
    op.drop_index(
        "ix_orch_scm_webhook_delivery_received",
        table_name="orch_scm_webhook_delivery",
    )
    op.drop_table("orch_scm_webhook_delivery")
    op.drop_table("orch_scm_project_config")
    return
