"""
.. module:: hardening.metrics
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-process metrics registry stub for Layer-2 M3 observability.

.. moduleauthor:: Code Craft AI LLC

A deliberately tiny in-process registry that service code uses to record
counters and latency samples. The ``7-metrics-ingest`` feature replaces
the backing store without callers changing. Tests inspect the registry
to verify emission without wiring a real backend.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from typing import Dict, List, Mapping, Tuple


_LOCK = threading.RLock()
_COUNTERS: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}
_SAMPLES: Dict[str, List[float]] = {}


def _freeze_labels(labels: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
    """
        Convert a label mapping into a hashable, sorted tuple.
    """
    rtnval = tuple(sorted((str(k), str(v)) for k, v in (labels or {}).items()))
    return rtnval


def increment_counter(
        *,
        name: str,
        labels: Mapping[str, str],
        by: int = 1
    ) -> None:
    """
        Increment a named counter by ``by``.

        :param name: Counter name (e.g. ``project.create.ok``).
        :param labels: Optional label map.
        :param by: Increment delta.

        :returns: None.
    """
    key = (name, _freeze_labels(labels))
    with _LOCK:
        current = _COUNTERS.get(key, 0)
        _COUNTERS[key] = current + int(by)
    return


def record_latency(*, name: str, latency_ms: float) -> None:
    """
        Append a latency sample to the named histogram.

        :param name: Histogram name.
        :param latency_ms: Latency in milliseconds.

        :returns: None.
    """
    with _LOCK:
        bucket = _SAMPLES.setdefault(name, [])
        bucket.append(float(latency_ms))
    return


def counter_value(*, name: str, labels: Mapping[str, str]) -> int:
    """
        Return the current value of a counter.
    """
    key = (name, _freeze_labels(labels))
    with _LOCK:
        rtnval = int(_COUNTERS.get(key, 0))
    return rtnval


def sample_count(*, name: str) -> int:
    """
        Return the count of samples recorded under ``name``.
    """
    with _LOCK:
        rtnval = len(_SAMPLES.get(name, []))
    return rtnval


def reset_for_testing() -> None:
    """
        Clear all counters and samples. Test-only.
    """
    with _LOCK:
        _COUNTERS.clear()
        _SAMPLES.clear()
    return
