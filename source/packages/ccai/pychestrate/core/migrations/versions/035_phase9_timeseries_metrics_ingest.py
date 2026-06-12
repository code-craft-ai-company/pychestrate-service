"""
Add Phase-9 / 0-timeseries-backend M1 table.

Revision ID: 035_phase9_timeseries_metrics_ingest
Revises: 034_phase8_extension_sandbox
Create Date: 2026-04-25

Adds:

- ``metrics_timeseries_sample`` (the native PG driver's
  storage table). The metric registry + ingest extensions are
  in-memory at M1; M2 introduces a registry catalog table.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "035_phase9_timeseries_metrics_ingest"
down_revision = "034_phase8_extension_sandbox"
branch_labels = None
depends_on = None


def upgrade():
    """
        Create the timeseries-sample table.
    """
    op.create_table(
        "metrics_timeseries_sample",
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "label_signature",
            sa.VARCHAR(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("sample_id"),
    )
    op.create_index(
        "ix_metrics_timeseries_sample_metric_observed",
        "metrics_timeseries_sample",
        ["metric_name", "observed_at"],
    )
    op.create_index(
        "ix_metrics_timeseries_sample_metric_signature",
        "metrics_timeseries_sample",
        ["metric_name", "label_signature"],
    )
    return


def downgrade():
    """
        Drop the timeseries-sample table.
    """
    op.drop_index(
        "ix_metrics_timeseries_sample_metric_signature",
        table_name="metrics_timeseries_sample",
    )
    op.drop_index(
        "ix_metrics_timeseries_sample_metric_observed",
        table_name="metrics_timeseries_sample",
    )
    op.drop_table("metrics_timeseries_sample")
    return
