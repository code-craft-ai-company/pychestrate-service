"""
.. module:: metrics.timeseries.factories.driver_protocol
    :synopsis: ``timeseries_driver`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Mapping

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class TimeseriesDriverProtocol(FactoryProtocolBase):
    """
        Contract for ``timeseries_driver`` extensions. The
        active driver is selected at startup from the registry
        in PRECEDENCE order. M1 ships only the native Postgres
        reference; M2 widens to Prometheus / Influx / Timescale
        through additional factory implementations.
    """

    factory_protocol_name: str = "timeseries_driver"
    protocol_schema_version: int = 1

    @classmethod
    def driver_name(cls) -> str:
        """
            Stable identifier for the driver.
        """
        raise NotImplementedError("Subclasses must implement driver_name")

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
        """
            Persist one sample into the driver's backend.
        """
        raise NotImplementedError("Subclasses must implement write_sample")
