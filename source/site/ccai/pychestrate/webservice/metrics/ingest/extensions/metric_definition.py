"""
.. module:: metrics.ingest.extensions.metric_definition
    :synopsis: ``MetricDefinitionExtension`` resource base class.

Each :class:`MetricDefinitionExtension` subclass declares a
single :class:`MetricDefinition` plus the bus topic + label
extractor that drives writes from
``entity.*`` events into the timeseries facade.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from typing import Any, Mapping

from ccai.pychestrate.webservice.extensions.resource_extension import (
    ResourceExtension,
)
from ccai.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
)


class MetricEmissionKind(str, enum.Enum):
    """
        How a single source-event becomes a sample.
    """
    COUNTER_INCREMENT = "counter_increment"
    GAUGE_SET = "gauge_set"


class MetricDefinitionExtension(ResourceExtension):
    """
        Base class for metric-definition resource extensions.

        Subclasses set ``definition`` (frozen
        :class:`MetricDefinition`), ``source_topic`` (the
        ``entity.*`` bus topic to subscribe to), and
        ``emission_kind`` (counter delta vs gauge set), then
        implement :meth:`extract_labels` (and optionally
        :meth:`extract_value`) to translate the event payload
        into a sample.
    """

    is_published: bool = True
    published_docs_url: str = (
        "/docs/extensions/resources/MetricDefinitionExtension.html"
    )
    published_reference: str = (
        "ccai.pychestrate.webservice.metrics.ingest.extensions.reservation_granted_counter"
        ".ResourceReservationGrantedCounter"
    )

    @classmethod
    def metric_name(cls) -> str:
        """
            Stable identifier used by :class:`MetricRegistry`.
        """
        raise NotImplementedError("Subclasses must implement metric_name")

    @classmethod
    def definition(cls) -> MetricDefinition:
        """
            Frozen :class:`MetricDefinition` describing the
            metric.
        """
        raise NotImplementedError("Subclasses must implement definition")

    @classmethod
    def source_topic(cls) -> str:
        """
            ``entity.*`` topic to subscribe to.
        """
        raise NotImplementedError("Subclasses must implement source_topic")

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        """
            ``counter_increment`` or ``gauge_set``.
        """
        raise NotImplementedError("Subclasses must implement emission_kind")

    @classmethod
    def extract_labels(
            cls,
            *,
            event_payload: Mapping[str, Any]
        ) -> Mapping[str, str]:
        """
            Translate the event payload into a label dict
            matching the declared label_names.
        """
        raise NotImplementedError("Subclasses must implement extract_labels")

    @classmethod
    def extract_value(
            cls,
            *,
            event_payload: Mapping[str, Any]
        ) -> float:
        """
            Translate the event payload into a numeric value.
            The default implementation returns 1.0 — suitable
            for ``counter_increment`` extensions counting
            arrivals; gauge subclasses override.
        """
        rtnval = 1.0
        return rtnval
