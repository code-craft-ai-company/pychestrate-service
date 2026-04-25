"""
.. module:: metrics.ingest.extensions.reservation_granted_counter
    :synopsis: ResourceReservationGrantedCounter — reference metric extension.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping

from automojo.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
    MetricEmissionKind,
)
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
)


METRIC_NAME: str = "pychestrate_resource_reservation_granted_total"
SOURCE_TOPIC: str = "entity.reservation.granted"


class ResourceReservationGrantedCounter(MetricDefinitionExtension):
    """
        Counter that increments for every ``entity.reservation.granted``
        bus event. Labels: ``project_id``, ``resource_id``, ``mode``.
        Demonstrates the M1 metric-extension surface.
    """

    @classmethod
    def metric_name(cls) -> str:
        rtnval = METRIC_NAME
        return rtnval

    @classmethod
    def definition(cls) -> MetricDefinition:
        rtnval = MetricDefinition(
            name=METRIC_NAME,
            kind=MetricKind.COUNTER,
            label_names=("project_id", "resource_id", "mode"),
            help_text="Number of reservation grants observed on the bus.",
            cardinality_max=10000,
        )
        return rtnval

    @classmethod
    def source_topic(cls) -> str:
        rtnval = SOURCE_TOPIC
        return rtnval

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        rtnval = MetricEmissionKind.COUNTER_INCREMENT
        return rtnval

    @classmethod
    def extract_labels(
            cls,
            *,
            event_payload: Mapping[str, Any]
        ) -> Mapping[str, str]:
        rtnval = {
            "project_id": str(event_payload.get("project_id", "")),
            "resource_id": str(event_payload.get("resource_id", "")),
            "mode": str(event_payload.get("mode", "")),
        }
        return rtnval

    @classmethod
    def extract_value(
            cls,
            *,
            event_payload: Mapping[str, Any]
        ) -> float:
        rtnval = 1.0
        return rtnval
