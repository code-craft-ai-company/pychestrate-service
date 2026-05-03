"""
.. module:: metrics.timeseries.facade
    :synopsis: TimeseriesFacade — process-singleton write surface.

Owns:

* :class:`MetricRegistry` — name → :class:`MetricDefinition`.
* per-metric cardinality counters (``label_signature -> seen``).
* a bounded write buffer surfaced for M2 driver-degradation
  resilience (M1 just passes writes through to the active
  driver).

The facade resolves the active :class:`TimeseriesDriverProtocol`
through the extension registry every write — late binding lets
operators swap drivers in tests without restarting the
authority.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import hashlib
import json
import os
import threading

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, FrozenSet, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.metrics.timeseries.errors import (
    MetricCardinalityExceededError,
    MetricLabelInvalidError,
    MetricUnknownError,
    TimeseriesDriverNotFoundError,
)
from automojo.pychestrate.webservice.metrics.timeseries.factories.driver_protocol import (
    TimeseriesDriverProtocol,
)


TIMESERIES_DRIVER_PROTOCOL: str = "timeseries_driver"
DEFAULT_BUFFER_MAX_SAMPLES: int = 4096
DEFAULT_CARDINALITY_MAX: int = 10000


class MetricKind(str, enum.Enum):
    """
        M1 supports counters and gauges. Histograms land in M2
        once the bucket-aware write path is in place.
    """
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True)
class MetricDefinition:
    """
        Frozen-dataclass description of a metric.

        :param name: Stable identifier.
        :param kind: Counter / gauge / histogram.
        :param label_names: Tuple of declared label names.
        :param help_text: Human-readable description.
        :param cardinality_max: Hard cap on distinct
                                label-tuples per metric.
        :param buckets: Histogram bucket edges (M2 only); empty
                        for counter / gauge.
    """
    name: str
    kind: MetricKind
    label_names: Tuple[str, ...] = ()
    help_text: str = ""
    cardinality_max: int = DEFAULT_CARDINALITY_MAX
    buckets: Tuple[float, ...] = ()


@dataclass(frozen=True)
class Sample:
    """
        Frozen-dataclass view of a buffered sample.
    """
    metric_name: str
    label_signature: str
    labels: Mapping[str, str]
    value: float
    observed_at: datetime


class MetricRegistry:
    """
        Process-singleton mapping metric name to
        :class:`MetricDefinition`. The metrics-ingest layer
        seeds the registry at startup; tests register through
        :func:`register_definition`.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._definitions: Dict[str, MetricDefinition] = {}
        return

    def register(self, *, definition: MetricDefinition) -> None:
        """
            Insert (or overwrite) a definition.
        """
        with self._lock:
            self._definitions[definition.name] = definition
        return

    def find(self, *, name: str) -> Optional[MetricDefinition]:
        with self._lock:
            rtnval = self._definitions.get(name, None)
        return rtnval

    def list_names(self) -> Tuple[str, ...]:
        with self._lock:
            rtnval = tuple(sorted(self._definitions.keys()))
        return rtnval

    def list_definitions(self) -> Tuple[MetricDefinition, ...]:
        with self._lock:
            rtnval = tuple(
                self._definitions[name]
                for name in sorted(self._definitions.keys())
            )
        return rtnval

    def reset(self) -> None:
        with self._lock:
            self._definitions.clear()
        return


class TimeseriesFacade:
    """
        Process-singleton surface every write goes through.
    """

    def __init__(
            self,
            *,
            registry: MetricRegistry,
            buffer_max_samples: int = DEFAULT_BUFFER_MAX_SAMPLES
        ) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._registry: MetricRegistry = registry
        self._buffer: Deque[Sample] = deque(maxlen=buffer_max_samples)
        self._cardinality: Dict[str, set] = {}
        return

    @property
    def registry(self) -> MetricRegistry:
        rtnval = self._registry
        return rtnval

    def write_counter(
            self,
            *,
            db_session: DbSession,
            name: str,
            delta: float,
            labels: Mapping[str, str]
        ) -> Sample:
        """
            Record a counter delta. Validates name + labels +
            cardinality before dispatching to the active
            driver.

            :raises: MetricUnknownError, MetricLabelInvalidError,
                     MetricCardinalityExceededError,
                     TimeseriesDriverNotFoundError.
        """
        rtnval = self._write_internal(
            db_session=db_session,
            name=name,
            kind_required=MetricKind.COUNTER,
            value=delta,
            labels=labels,
        )
        return rtnval

    def write_gauge(
            self,
            *,
            db_session: DbSession,
            name: str,
            value: float,
            labels: Mapping[str, str]
        ) -> Sample:
        """
            Record a gauge value. Validates name + labels +
            cardinality before dispatching to the active
            driver.
        """
        rtnval = self._write_internal(
            db_session=db_session,
            name=name,
            kind_required=MetricKind.GAUGE,
            value=value,
            labels=labels,
        )
        return rtnval

    def buffer_snapshot(self) -> Tuple[Sample, ...]:
        """
            Return a snapshot of the in-memory buffer. The
            buffer keeps the last ``buffer_max_samples`` writes
            for diagnostics and the M2 degradation-resilience
            replay path.
        """
        with self._lock:
            rtnval = tuple(self._buffer)
        return rtnval

    def cardinality_for(self, *, name: str) -> int:
        with self._lock:
            rtnval = len(self._cardinality.get(name, set()))
        return rtnval

    def reset(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._cardinality.clear()
        return

    def _write_internal(
            self,
            *,
            db_session: DbSession,
            name: str,
            kind_required: MetricKind,
            value: float,
            labels: Mapping[str, str]
        ) -> Sample:
        definition = self._registry.find(name=name)
        if definition is None:
            err_lines = ["Metric name is not registered."]
            err_lines.append("METRIC_NAME: {}".format(name))
            err_msg = os.linesep.join(err_lines)
            raise MetricUnknownError(err_msg) from None

        if definition.kind != kind_required:
            err_lines = [
                "Metric kind mismatch: write call requires {}.".format(
                    kind_required.value,
                ),
            ]
            err_lines.append("METRIC_NAME: {}".format(name))
            err_lines.append("DECLARED_KIND: {}".format(definition.kind.value))
            err_msg = os.linesep.join(err_lines)
            raise MetricLabelInvalidError(err_msg) from None

        signature = self._validate_labels(
            definition=definition, labels=labels,
        )
        self._update_cardinality(
            definition=definition, signature=signature,
        )

        observed_at = utc_now()
        driver_cls = _resolve_driver()
        driver_cls.write_sample(
            db_session=db_session,
            metric_name=name,
            label_signature=signature,
            labels=dict(labels),
            value=value,
            observed_at=observed_at,
        )
        sample = Sample(
            metric_name=name,
            label_signature=signature,
            labels=dict(labels),
            value=value,
            observed_at=observed_at,
        )
        with self._lock:
            self._buffer.append(sample)
        return sample

    def _validate_labels(
            self,
            *,
            definition: MetricDefinition,
            labels: Mapping[str, str]
        ) -> str:
        declared = set(definition.label_names)
        provided = set(labels.keys())
        missing = declared - provided
        extras = provided - declared
        if len(missing) > 0 or len(extras) > 0:
            err_lines = ["Metric labels do not match declaration."]
            err_lines.append("METRIC_NAME: {}".format(definition.name))
            if len(missing) > 0:
                err_lines.append(
                    "MISSING: {}".format(", ".join(sorted(missing))),
                )
            if len(extras) > 0:
                err_lines.append(
                    "EXTRAS: {}".format(", ".join(sorted(extras))),
                )
            err_msg = os.linesep.join(err_lines)
            raise MetricLabelInvalidError(err_msg) from None

        for key, value in labels.items():
            if not isinstance(value, str):
                err_lines = ["Metric label values must be strings."]
                err_lines.append("METRIC_NAME: {}".format(definition.name))
                err_lines.append("LABEL: {}".format(key))
                err_lines.append("VALUE_TYPE: {}".format(type(value).__name__))
                err_msg = os.linesep.join(err_lines)
                raise MetricLabelInvalidError(err_msg) from None

        canonical = json.dumps(
            {key: labels[key] for key in sorted(labels.keys())},
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        rtnval = digest[:32]
        return rtnval

    def _update_cardinality(
            self,
            *,
            definition: MetricDefinition,
            signature: str
        ) -> None:
        with self._lock:
            seen = self._cardinality.setdefault(definition.name, set())
            if signature in seen:
                return
            if len(seen) >= definition.cardinality_max:
                err_lines = ["Metric cardinality_max would be exceeded."]
                err_lines.append("METRIC_NAME: {}".format(definition.name))
                err_lines.append("CARDINALITY_MAX: {}".format(
                    definition.cardinality_max,
                ))
                err_lines.append("CURRENT: {}".format(len(seen)))
                err_msg = os.linesep.join(err_lines)
                raise MetricCardinalityExceededError(err_msg) from None
            seen.add(signature)
        return


def _resolve_driver() -> Type[TimeseriesDriverProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=TIMESERIES_DRIVER_PROTOCOL,
    )
    if len(candidates) == 0:
        err_lines = ["No timeseries_driver implementation is registered."]
        err_msg = os.linesep.join(err_lines)
        raise TimeseriesDriverNotFoundError(err_msg) from None
    rtnval = candidates[0]
    return rtnval


_REGISTRY_LOCK = threading.RLock()
_REGISTRY: Optional[MetricRegistry] = None
_FACADE: Optional[TimeseriesFacade] = None


def get_metric_registry() -> MetricRegistry:
    """
        Process-singleton metric registry.
    """
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = MetricRegistry()
        rtnval = _REGISTRY
    return rtnval


def get_facade() -> TimeseriesFacade:
    """
        Process-singleton facade.
    """
    global _FACADE
    with _REGISTRY_LOCK:
        if _FACADE is None:
            _FACADE = TimeseriesFacade(registry=get_metric_registry())
        rtnval = _FACADE
    return rtnval


def reset_for_testing() -> None:
    """
        Drop the registry + facade singletons. Tests call this
        between cases to isolate from cross-test bleed.
    """
    global _REGISTRY, _FACADE
    with _REGISTRY_LOCK:
        if _REGISTRY is not None:
            _REGISTRY.reset()
        if _FACADE is not None:
            _FACADE.reset()
        _REGISTRY = None
        _FACADE = None
    return
