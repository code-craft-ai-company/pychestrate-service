"""
.. module:: metrics.ingest.service
    :synopsis: Metrics-ingest facade — extension catalog + emit translator.

M1 ships:

* :func:`reload_definitions_from_extensions` — walks every
  registered :class:`MetricDefinitionExtension` and pushes its
  :class:`MetricDefinition` into the timeseries registry.
  Service-start path; M2 wires a hot-reload subscriber on
  ``extension.reloaded``.
* :func:`emit_metric_for_event` — translate one bus event
  payload into a write through the facade. Looks up the
  extension by ``metric_name`` and dispatches by emission
  kind.
* :func:`list_metric_extensions` — read helper.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.metrics.ingest.errors import (
    MetricExtensionUnknownError,
)
from ccai.pychestrate.webservice.metrics.ingest.events import (
    MetricsIngestEventTopics,
)
from ccai.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
    MetricEmissionKind,
)
from ccai.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    Sample,
    get_facade,
    get_metric_registry,
)
from ccai.pychestrate.webservice.metrics.timeseries.service import (
    register_definition,
)


@dataclass(frozen=True)
class MetricExtensionView:
    """
        Caller-facing read-model describing a registered
        metric extension.
    """
    metric_name: str
    source_topic: str
    emission_kind: str
    definition: MetricDefinition


@dataclass(frozen=True)
class EmittedSampleView:
    """
        Caller-facing read-model surfacing one emitted sample
        plus the source-event correlation.
    """
    metric_name: str
    label_signature: str
    labels: Mapping[str, str]
    value: float
    observed_at: datetime
    source_topic: str


def reload_definitions_from_extensions(
        *,
        db_session: DbSession
    ) -> Tuple[MetricExtensionView, ...]:
    """
        Walk every registered
        :class:`MetricDefinitionExtension` and seed the
        timeseries registry. Emits METRICS_REGISTRY_LOADED.
    """
    registry = get_metric_registry()
    candidates = list_resource_extensions(
        base_class=MetricDefinitionExtension,
    )
    views: List[MetricExtensionView] = []
    for ext_cls in candidates:
        definition = ext_cls.definition()
        registry.register(definition=definition)
        views.append(
            MetricExtensionView(
                metric_name=ext_cls.metric_name(),
                source_topic=ext_cls.source_topic(),
                emission_kind=ext_cls.emission_kind().value,
                definition=definition,
            )
        )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=MetricsIngestEventTopics.METRICS_REGISTRY_LOADED,
            payload={"metric_count": len(views)},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = tuple(views)
    return rtnval


def emit_metric_for_event(
        *,
        db_session: DbSession,
        metric_name: str,
        event_payload: Mapping[str, Any]
    ) -> EmittedSampleView:
    """
        Translate one bus event payload into a write through
        the facade. The bus subscriber path that auto-invokes
        this for matching topics lands in M2; M1 callers wire
        it explicitly per-test or per-emission point.

        :raises: MetricExtensionUnknownError when the
                 ``metric_name`` has no registered extension.
    """
    extension_cls = _resolve_extension(metric_name=metric_name)
    labels = extension_cls.extract_labels(event_payload=event_payload)
    value = extension_cls.extract_value(event_payload=event_payload)
    facade = get_facade()
    if extension_cls.emission_kind() == MetricEmissionKind.COUNTER_INCREMENT:
        sample = facade.write_counter(
            db_session=db_session,
            name=extension_cls.metric_name(),
            delta=value,
            labels=labels,
        )
    else:
        sample = facade.write_gauge(
            db_session=db_session,
            name=extension_cls.metric_name(),
            value=value,
            labels=labels,
        )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=MetricsIngestEventTopics.SAMPLE_EMITTED,
            payload={
                "metric_name": sample.metric_name,
                "label_signature": sample.label_signature,
                "value": sample.value,
                "source_topic": extension_cls.source_topic(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = EmittedSampleView(
        metric_name=sample.metric_name,
        label_signature=sample.label_signature,
        labels=dict(sample.labels),
        value=sample.value,
        observed_at=sample.observed_at,
        source_topic=extension_cls.source_topic(),
    )
    return rtnval


def list_metric_extensions() -> Tuple[MetricExtensionView, ...]:
    """
        Read every registered :class:`MetricDefinitionExtension`.
    """
    candidates = list_resource_extensions(
        base_class=MetricDefinitionExtension,
    )
    rtnval = tuple(
        MetricExtensionView(
            metric_name=ext_cls.metric_name(),
            source_topic=ext_cls.source_topic(),
            emission_kind=ext_cls.emission_kind().value,
            definition=ext_cls.definition(),
        )
        for ext_cls in candidates
    )
    return rtnval


def _resolve_extension(
        *, metric_name: str
    ) -> Type[MetricDefinitionExtension]:
    candidates = list_resource_extensions(
        base_class=MetricDefinitionExtension,
    )
    for ext_cls in candidates:
        if ext_cls.metric_name() == metric_name:
            return ext_cls
    err_lines = ["No registered MetricDefinitionExtension for name."]
    err_lines.append("METRIC_NAME: {}".format(metric_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(ext_cls.metric_name() for ext_cls in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise MetricExtensionUnknownError(err_msg) from None
