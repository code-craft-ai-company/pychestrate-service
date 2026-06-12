"""
Add Phase-9 / 7-project-dashboards + 7-alerts-budgets M1 tables.

Revision ID: 036_phase9_dashboards_alerts
Revises: 035_phase9_timeseries_metrics_ingest
Create Date: 2026-04-25

Adds:

- ``metrics_dashboard``.
- ``metrics_alert_rule``.
- ``metrics_alert_live_state``.

Plus the ``metrics_alert_severity`` and
``metrics_alert_state`` enums.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "036_phase9_dashboards_alerts"
down_revision = "035_phase9_timeseries_metrics_ingest"
branch_labels = None
depends_on = None


ALERT_SEVERITY_ENUM = "metrics_alert_severity"
ALERT_SEVERITY_VALUES = ("INFO", "WARNING", "CRITICAL")

ALERT_STATE_ENUM = "metrics_alert_state"
ALERT_STATE_VALUES = ("UNKNOWN", "OK", "FIRING")


def upgrade():
    """
        Create the dashboard + alert tables.
    """
    op.create_table(
        "metrics_dashboard",
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "owner_principal_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "grid_columns_max", sa.Integer(), nullable=False, server_default="12",
        ),
        sa.Column("tiles", sa.JSON(), nullable=False, server_default="[]"),
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
        sa.PrimaryKeyConstraint("dashboard_id"),
        sa.UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_dashboard_project_name",
        ),
    )
    op.create_index(
        "ix_metrics_dashboard_project",
        "metrics_dashboard",
        ["project_id"],
    )

    op.create_table(
        "metrics_alert_rule",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.VARCHAR(64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "severity",
            sa.Enum(*ALERT_SEVERITY_VALUES, name=ALERT_SEVERITY_ENUM),
            nullable=False,
            server_default="WARNING",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "notification_targets",
            sa.JSON(),
            nullable=False,
            server_default="[]",
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
        sa.PrimaryKeyConstraint("rule_id"),
        sa.UniqueConstraint(
            "project_id", "name",
            name="uq_metrics_alert_rule_project_name",
        ),
    )
    op.create_index(
        "ix_metrics_alert_rule_project_enabled",
        "metrics_alert_rule",
        ["project_id", "enabled"],
    )
    op.create_index(
        "ix_metrics_alert_rule_kind",
        "metrics_alert_rule",
        ["kind"],
    )

    op.create_table(
        "metrics_alert_live_state",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum(*ALERT_STATE_VALUES, name=ALERT_STATE_ENUM),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("last_value", sa.JSON(), nullable=True),
        sa.Column("last_threshold", sa.JSON(), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_state_changed_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fire_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "resolve_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.PrimaryKeyConstraint("rule_id"),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["metrics_alert_rule.rule_id"],
            ondelete="CASCADE",
        ),
    )
    return


def downgrade():
    """
        Drop the dashboard + alert tables and the new enums.
    """
    op.drop_table("metrics_alert_live_state")

    op.drop_index(
        "ix_metrics_alert_rule_kind", table_name="metrics_alert_rule",
    )
    op.drop_index(
        "ix_metrics_alert_rule_project_enabled",
        table_name="metrics_alert_rule",
    )
    op.drop_table("metrics_alert_rule")

    op.drop_index(
        "ix_metrics_dashboard_project", table_name="metrics_dashboard",
    )
    op.drop_table("metrics_dashboard")

    sa.Enum(name=ALERT_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=ALERT_SEVERITY_ENUM).drop(op.get_bind(), checkfirst=True)
    return
