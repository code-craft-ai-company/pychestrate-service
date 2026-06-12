"""
Add Phase-9 / 7-slo-views M1 tables.

Revision ID: 037_phase9_slo_views
Revises: 036_phase9_dashboards_alerts
Create Date: 2026-04-25

Adds:

- ``metrics_slo``.
- ``metrics_slo_burn_rate_state`` (FK CASCADE on the SLO).
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "037_phase9_slo_views"
down_revision = "036_phase9_dashboards_alerts"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the SLO catalog tables.
    """
    op.create_table(
        "metrics_slo",
        sa.Column("slo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.VARCHAR(64), nullable=False),
        sa.Column("target", sa.Float(), nullable=False, server_default="0.99"),
        sa.Column(
            "window_seconds",
            sa.Integer(),
            nullable=False,
            server_default="2592000",
        ),
        sa.Column(
            "definition_config", sa.JSON(), nullable=False, server_default="{}",
        ),
        sa.Column(
            "default_notification_route_key", sa.VARCHAR(128), nullable=True,
        ),
        sa.Column(
            "auto_attach_burn_rate_alerts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint("slo_id"),
        sa.UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_slo_project_name",
        ),
    )
    op.create_index(
        "ix_metrics_slo_project", "metrics_slo", ["project_id"],
    )
    op.create_index(
        "ix_metrics_slo_kind", "metrics_slo", ["kind"],
    )

    op.create_table(
        "metrics_slo_burn_rate_state",
        sa.Column("slo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "last_fast_burn_rate",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "last_slow_burn_rate",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "last_fast_over_since", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "last_slow_over_since", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("slo_id"),
        sa.ForeignKeyConstraint(
            ["slo_id"], ["metrics_slo.slo_id"], ondelete="CASCADE",
        ),
    )
    return


def downgrade():
    """
        Drop the SLO tables.
    """
    op.drop_table("metrics_slo_burn_rate_state")
    op.drop_index("ix_metrics_slo_kind", table_name="metrics_slo")
    op.drop_index("ix_metrics_slo_project", table_name="metrics_slo")
    op.drop_table("metrics_slo")
    return
