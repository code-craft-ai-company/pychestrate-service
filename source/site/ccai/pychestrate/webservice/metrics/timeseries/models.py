"""
.. module:: metrics.timeseries.models
    :synopsis: SQLAlchemy model for timeseries samples.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    String,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class TimeseriesSample(PychestratePhase1Base, SerializableModel):
    """
        One timeseries sample row. The native driver writes
        every sample inline; M2 introduces partitioning and the
        Timescale-on-top hypertable variant.
    """

    __tablename__ = "metrics_timeseries_sample"

    sample_id = Column(UUIDType(binary=False), primary_key=True)
    metric_name = Column(String(128), nullable=False)
    label_signature = Column(String(64), nullable=False, default="")
    labels = Column(JSON, nullable=False, default=dict)
    value = Column(Float, nullable=False, default=0.0)
    observed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_metrics_timeseries_sample_metric_observed",
            "metric_name", "observed_at",
        ),
        Index(
            "ix_metrics_timeseries_sample_metric_signature",
            "metric_name", "label_signature",
        ),
    )
