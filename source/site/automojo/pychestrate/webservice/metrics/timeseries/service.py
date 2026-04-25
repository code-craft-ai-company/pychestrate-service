"""
.. module:: metrics.timeseries.service
    :synopsis: Timeseries-backend public service helpers.

Thin wrappers around the :class:`TimeseriesFacade` singleton:

* :func:`register_definition` — add a :class:`MetricDefinition`
  to the registry; emits DEFINITION_REGISTERED.
* :func:`write_counter` / :func:`write_gauge` — facade-backed
  writes the metrics-ingest layer calls.
* :func:`list_definitions` — read helper.
* :func:`list_samples_for_metric` — read helper that returns
  the latest samples persisted by the active driver.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Mapping, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.metrics.timeseries import repository
from automojo.pychestrate.webservice.metrics.timeseries.events import (
    TimeseriesEventTopics,
)
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    Sample,
    get_facade,
    get_metric_registry,
)


LIST_SAMPLES_DEFAULT_LIMIT: int = 200


@dataclass(frozen=True)
class SampleView:
    """
        Caller-facing read-model for a persisted sample.
    """
    sample_id: str
    metric_name: str
    label_signature: str
    labels: Mapping[str, str]
    value: float
    observed_at: datetime


def register_definition(
        *,
        db_session: DbSession,
        definition: MetricDefinition
    ) -> MetricDefinition:
    """
        Register a definition with the in-memory registry +
        emit DEFINITION_REGISTERED.
    """
    registry = get_metric_registry()
    registry.register(definition=definition)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=TimeseriesEventTopics.DEFINITION_REGISTERED,
            payload={
                "metric_name": definition.name,
                "kind": definition.kind.value,
                "label_names": list(definition.label_names),
                "cardinality_max": definition.cardinality_max,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = definition
    return rtnval


def write_counter(
        *,
        db_session: DbSession,
        name: str,
        delta: float,
        labels: Mapping[str, str]
    ) -> Sample:
    """
        Counter delta. Validates name + labels + cardinality
        through the facade.
    """
    facade = get_facade()
    rtnval = facade.write_counter(
        db_session=db_session, name=name, delta=delta, labels=labels,
    )
    return rtnval


def write_gauge(
        *,
        db_session: DbSession,
        name: str,
        value: float,
        labels: Mapping[str, str]
    ) -> Sample:
    """
        Gauge value.
    """
    facade = get_facade()
    rtnval = facade.write_gauge(
        db_session=db_session, name=name, value=value, labels=labels,
    )
    return rtnval


def list_definitions() -> Tuple[MetricDefinition, ...]:
    """
        Return every registered :class:`MetricDefinition` in
        sorted-name order.
    """
    rtnval = get_metric_registry().list_definitions()
    return rtnval


def list_samples_for_metric(
        *,
        db_session: DbSession,
        metric_name: str,
        limit: int = LIST_SAMPLES_DEFAULT_LIMIT
    ) -> List[SampleView]:
    """
        Read newest-first samples persisted by the active
        driver.
    """
    rows = repository.list_samples_for_metric(
        db_session=db_session, metric_name=metric_name, limit=limit,
    )
    rtnval: List[SampleView] = []
    for row in rows:
        rtnval.append(
            SampleView(
                sample_id=str(row.sample_id),
                metric_name=row.metric_name,
                label_signature=row.label_signature,
                labels=dict(row.labels or {}),
                value=row.value,
                observed_at=row.observed_at,
            )
        )
    return rtnval
