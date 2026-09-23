"""
.. module:: system.prometheus
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A small in-process metric registry rendered in the
               Prometheus text exposition format (0.0.4).

.. moduleauthor:: Code Craft AI LLC

The service has no metrics client library, so this module provides the
three shapes ``/metrics`` needs:

* :class:`CounterMetric` -- monotonically increasing, per label set;
* :class:`HistogramMetric` -- cumulative buckets + sum + count;
* :class:`MetricFamily` -- a gauge (or any family) whose samples are
  computed at scrape time by a collector.

Counters and histograms live in the worker process; a multi-worker
deployment exposes one set per process (each series carries a ``pid``
label via the collectors that add it), which Prometheus sums.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import math
import threading

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


#: Content type of the text exposition format.
EXPOSITION_CONTENT_TYPE: str = "text/plain; version=0.0.4; charset=utf-8"

#: Default latency buckets (seconds), per the 0-web-app-host design.
DEFAULT_LATENCY_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)


def escape_label_value(value: str) -> str:
    """
        Escape a label value for the exposition format.

        :param value: Raw value.

        :returns: Value with ``\\``, ``"`` and newlines escaped.
    """
    rtnval = str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    return rtnval


def format_value(value: float) -> str:
    """
        Format a sample value (integers without a decimal point,
        infinities as ``+Inf`` / ``-Inf``).

        :param value: Sample value.

        :returns: Text form.
    """
    if math.isinf(value):
        rtnval = "+Inf" if value > 0 else "-Inf"
        return rtnval
    if math.isnan(value):
        return "NaN"
    if float(value).is_integer() and abs(value) < 1e15:
        rtnval = str(int(value))
        return rtnval
    rtnval = repr(float(value))
    return rtnval


def format_labels(labels: Sequence[Tuple[str, str]]) -> str:
    """
        Render a label set.

        :param labels: ``(name, value)`` pairs.

        :returns: ``{a="1",b="2"}`` or ``""``.
    """
    if len(labels) == 0:
        return ""
    body = ",".join('{}="{}"'.format(name, escape_label_value(value)) for name, value in labels)
    rtnval = "{" + body + "}"
    return rtnval


@dataclass
class Sample:
    """
        One exposition line.

        :ivar name: Sample name (family name, or with a suffix).
        :ivar labels: ``(name, value)`` pairs.
        :ivar value: Sample value.
    """
    name: str
    labels: List[Tuple[str, str]]
    value: float


@dataclass
class MetricFamily:
    """
        A metric family with its samples.

        :ivar name: Family name.
        :ivar kind: ``counter`` | ``gauge`` | ``histogram``.
        :ivar help: HELP text.
        :ivar samples: Samples.
    """
    name: str
    kind: str
    help: str
    samples: List[Sample] = field(default_factory=list)

    def add(self, *, value: float, labels: Optional[Sequence[Tuple[str, str]]] = None, suffix: str = "") -> None:
        """
            Append a sample.

            :param value: Sample value.
            :param labels: ``(name, value)`` pairs.
            :param suffix: Name suffix (``_bucket`` / ``_sum`` / ``_count``).

            :returns: None.
        """
        self.samples.append(Sample(name=self.name + suffix, labels=list(labels or []), value=float(value)))
        return


class CounterMetric:
    """
        A process-local counter keyed by label values.
    """

    def __init__(self, *, name: str, help: str, label_names: Sequence[str]) -> None:
        self.name: str = name
        self.help: str = help
        self.label_names: Tuple[str, ...] = tuple(label_names)
        self._values: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()
        return

    def inc(self, *, labels: Sequence[str], amount: float = 1.0) -> None:
        """
            Increment the counter for one label set.

            :param labels: Label values, in ``label_names`` order.
            :param amount: Increment (>= 0).

            :returns: None.
        """
        key = tuple(str(value) for value in labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + float(amount)
        return

    def value(self, *, labels: Sequence[str]) -> float:
        """
            Current value for one label set.

            :param labels: Label values.

            :returns: Counter value (0 when never incremented).
        """
        with self._lock:
            rtnval = self._values.get(tuple(str(value) for value in labels), 0.0)
        return rtnval

    def collect(self, *, extra_labels: Sequence[Tuple[str, str]] = ()) -> MetricFamily:
        """
            Snapshot as a :class:`MetricFamily`.

            :param extra_labels: Labels appended to every sample.

            :returns: The family.
        """
        family = MetricFamily(name=self.name, kind="counter", help=self.help)
        with self._lock:
            items = sorted(self._values.items())
        for key, value in items:
            family.add(value=value, labels=list(zip(self.label_names, key)) + list(extra_labels))
        rtnval = family
        return rtnval

    def reset_for_testing(self) -> None:
        """
            Clear every value. Test-only.

            :returns: None.
        """
        with self._lock:
            self._values.clear()
        return


class HistogramMetric:
    """
        A process-local histogram keyed by label values.
    """

    def __init__(
            self,
            *,
            name: str,
            help: str,
            label_names: Sequence[str],
            buckets: Sequence[float] = DEFAULT_LATENCY_BUCKETS
        ) -> None:
        self.name: str = name
        self.help: str = help
        self.label_names: Tuple[str, ...] = tuple(label_names)
        self.buckets: Tuple[float, ...] = tuple(sorted(float(bound) for bound in buckets))
        self._series: Dict[Tuple[str, ...], List[float]] = {}
        self._lock = threading.Lock()
        return

    def observe(self, *, value: float, labels: Sequence[str] = ()) -> None:
        """
            Record one observation.

            :param value: Observed value.
            :param labels: Label values, in ``label_names`` order.

            :returns: None.
        """
        key = tuple(str(label) for label in labels)
        with self._lock:
            series = self._series.get(key, None)
            if series is None:
                # bucket counts..., sum, count
                series = [0.0] * (len(self.buckets) + 2)
                self._series[key] = series
            for index, bound in enumerate(self.buckets):
                if value <= bound:
                    series[index] += 1.0
            series[-2] += float(value)
            series[-1] += 1.0
        return

    def count(self, *, labels: Sequence[str] = ()) -> float:
        """
            Number of observations for one label set.

            :param labels: Label values.

            :returns: Observation count.
        """
        with self._lock:
            series = self._series.get(tuple(str(label) for label in labels), None)
            rtnval = series[-1] if series is not None else 0.0
        return rtnval

    def collect(self, *, extra_labels: Sequence[Tuple[str, str]] = ()) -> MetricFamily:
        """
            Snapshot as a :class:`MetricFamily` (cumulative buckets,
            ``+Inf``, ``_sum``, ``_count``).

            :param extra_labels: Labels appended to every sample.

            :returns: The family.
        """
        family = MetricFamily(name=self.name, kind="histogram", help=self.help)
        with self._lock:
            items = sorted((key, list(series)) for key, series in self._series.items())
        for key, series in items:
            base = list(zip(self.label_names, key)) + list(extra_labels)
            for index, bound in enumerate(self.buckets):
                family.add(value=series[index], labels=base + [("le", format_value(bound))], suffix="_bucket")
            family.add(value=series[-1], labels=base + [("le", "+Inf")], suffix="_bucket")
            family.add(value=series[-2], labels=base, suffix="_sum")
            family.add(value=series[-1], labels=base, suffix="_count")
        rtnval = family
        return rtnval

    def reset_for_testing(self) -> None:
        """
            Clear every series. Test-only.

            :returns: None.
        """
        with self._lock:
            self._series.clear()
        return


def render_exposition(*, families: Iterable[MetricFamily]) -> str:
    """
        Render families in the text exposition format. Families with no
        samples still get their HELP / TYPE lines.

        :param families: Families to render.

        :returns: Exposition text (ends with a newline).
    """
    lines: List[str] = []
    for family in families:
        lines.append("# HELP {} {}".format(family.name, family.help.replace("\\", "\\\\").replace("\n", "\\n")))
        lines.append("# TYPE {} {}".format(family.name, family.kind))
        for sample in family.samples:
            lines.append("{}{} {}".format(sample.name, format_labels(sample.labels), format_value(sample.value)))
    rtnval = "\n".join(lines) + "\n"
    return rtnval


__all__ = [
    "CounterMetric",
    "DEFAULT_LATENCY_BUCKETS",
    "EXPOSITION_CONTENT_TYPE",
    "HistogramMetric",
    "MetricFamily",
    "Sample",
    "escape_label_value",
    "format_labels",
    "format_value",
    "render_exposition",
]
