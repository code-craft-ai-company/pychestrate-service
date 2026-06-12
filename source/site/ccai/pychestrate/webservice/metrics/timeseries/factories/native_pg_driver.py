"""
.. module:: metrics.timeseries.factories.native_pg_driver
    :synopsis: NativePgTimeseriesDriver — reference SQL-backed driver.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Mapping

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.metrics.timeseries import repository
from ccai.pychestrate.webservice.metrics.timeseries.factories.driver_protocol import (
    TimeseriesDriverProtocol,
)


NATIVE_PG_DRIVER_NAME: str = "native-pg"


class NativePgTimeseriesDriver(TimeseriesDriverProtocol):
    """
        Reference SQL-backed driver. Persists every sample to
        ``metrics_timeseries_sample``. M2 introduces partitioning
        + a Timescale-on-top variant.
    """

    factory_protocol_name: str = "timeseries_driver"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def driver_name(cls) -> str:
        rtnval = NATIVE_PG_DRIVER_NAME
        return rtnval

    @classmethod
    def write_sample(
            cls,
            *,
            db_session: DbSession,
            metric_name: str,
            label_signature: str,
            labels: Mapping[str, str],
            value: float,
            observed_at: datetime
        ) -> None:
        repository.insert_sample(
            db_session=db_session,
            metric_name=metric_name,
            label_signature=label_signature,
            labels=dict(labels),
            value=value,
            observed_at=observed_at,
        )
        return
