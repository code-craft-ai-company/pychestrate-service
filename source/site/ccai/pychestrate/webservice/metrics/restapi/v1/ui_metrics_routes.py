"""
.. module:: metrics.restapi.v1.ui_metrics_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST route for ``POST /api/v1/_metrics/ui``.

.. moduleauthor:: Code Craft AI LLC

The site shell (9-site-shell) beacons client-side measurement
batches to this endpoint via ``navigator.sendBeacon`` -- one batch
per page view (flushed on ``pagehide``), plus one per 30 s of
activity on a long-lived page. The payload is validated, rate
limited, and the shell's known timing metrics from signed-in users
are aggregated into the process's Prometheus registry (served on
``/metrics`` as ``pychestrate_ui_shell_*``); unknown metric names
and client labels are not aggregated, so cardinality stays bounded.

Rate limiting (LD-03) is keyed on the session principal the session
middleware attached -- ``RATE_LIMIT_MAX_BATCHES_PER_USER`` batches per
user per minute, far above what a person clicking through pages
produces -- and every anonymous batch shares one
``RATE_LIMIT_MAX_BATCHES`` bucket (the shell only runs signed in, so
anonymous beacons are stragglers from expired sessions). It used to
key on ``request.remote_address``, which webworks requests do not
carry, so every client shared a single 12-per-minute bucket and
normal browsing drew 429s. The limiter is per worker process.

Wire shape:

.. code-block:: json

    [
        {
            "metric": "pychestrate_ui_shell_tti_seconds",
            "value": 0.187,
            "labels": {"route": "/admin/users"},
            "timestamp_ms": 1710000000000
        }
    ]

Malformed payloads return 400. A client over its budget gets 429.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import math
import os
import threading
import time

from typing import Any, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.system.prometheus import (
    CounterMetric,
    HistogramMetric,
    MetricFamily,
)


METRICS_PATH = "/_metrics/ui"

#: Cap on the per-batch entry count. Larger payloads are rejected
#: with HTTP 400. Sized to comfortably accommodate the client's
#: 100-entry buffer cap with some headroom for clock skew.
MAX_BATCH_SIZE = 200

#: Cap on a single metric name string length.
MAX_METRIC_NAME_LENGTH = 128

#: Cap on a single label key / value length.
MAX_LABEL_LENGTH = 128

#: Cap on the per-request label dictionary size.
MAX_LABEL_COUNT = 16

#: Rate limit window (seconds).
RATE_LIMIT_WINDOW_SECONDS = 60

#: Maximum batches per signed-in user per window. The shell sends one
#: batch per page view, so this is two page views a second, sustained
#: for a minute -- no person gets near it; a runaway client does.
RATE_LIMIT_MAX_BATCHES_PER_USER = 120

#: Maximum batches per window shared by every anonymous caller.
RATE_LIMIT_MAX_BATCHES = 60

#: Bucket key shared by all requests without a principal.
ANONYMOUS_BUCKET_KEY = "anonymous"

#: Buckets for the shell's timing histograms (seconds).
UI_TIMING_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

#: Timing observations above this are dropped as clock garbage.
MAX_UI_TIMING_SECONDS = 600.0

#: Counter increments above this per entry are dropped.
MAX_UI_COUNTER_INCREMENT = 1000.0

_UI_TIMING_METRICS = (
    "pychestrate_ui_shell_tti_seconds",
    "pychestrate_ui_shell_sidebar_render_duration_seconds",
    "pychestrate_ui_shell_navigation_permission_refetch_seconds",
    "pychestrate_ui_shell_palette_open_duration_seconds",
    "pychestrate_ui_shell_palette_fanout_duration_seconds",
)

_UI_COUNTER_METRICS = (
    "pychestrate_ui_shell_sidebar_entry_clicked_total",
)

#: The shell metric catalog (``SHELL_METRICS`` in metrics-beacon.js),
#: aggregated per worker process and exposed on /metrics.
UI_TIMING_HISTOGRAMS: Dict[str, HistogramMetric] = {
    name: HistogramMetric(
        name=name,
        help="Site-shell timing reported by signed-in browsers ({}).".format(name),
        label_names=(),
        buckets=UI_TIMING_BUCKETS,
    )
    for name in _UI_TIMING_METRICS
}

UI_COUNTERS: Dict[str, CounterMetric] = {
    name: CounterMetric(
        name=name,
        help="Site-shell event count reported by signed-in browsers ({}).".format(name),
        label_names=(),
    )
    for name in _UI_COUNTER_METRICS
}

_LOGGER = logging.getLogger("pychestrate.ui.shell.metrics")


class _RateLimiter:
    """
        In-process sliding-window rate limiter keyed by bucket key
        (``user:<id>`` or the shared anonymous key). Cheap -- a single
        dict + list per key.

        Not durable across processes; mirrored per gunicorn worker, so
        the effective cap is multiplied by the worker count.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        return

    def check_and_record(self, *, address: str, now: float, limit: int = RATE_LIMIT_MAX_BATCHES) -> bool:
        """
            Return True when the supplied key is under its limit and
            the current request should be counted.

            :param address: Bucket key.
            :param now: Monotonic-ish timestamp (seconds).
            :param limit: Batches allowed per window for this key.

            :returns: True if allowed; False if the limit is hit.
        """
        with self._lock:
            bucket = self._buckets.get(address)
            if bucket is None:
                bucket = []
                self._buckets[address] = bucket

            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            retained: List[float] = []
            for timestamp in bucket:
                if timestamp >= cutoff:
                    retained.append(timestamp)

            if len(retained) >= limit:
                self._buckets[address] = retained
                rtnval = False
                return rtnval

            retained.append(now)
            self._buckets[address] = retained
        rtnval = True
        return rtnval


_RATE_LIMITER = _RateLimiter()


def _rate_limit_bucket(request: Request) -> Tuple[str, int, bool]:
    """
        Pick the rate-limit bucket for a beacon: the signed-in user the
        session middleware resolved, or the one bucket every anonymous
        caller shares (no client-supplied header decides the key).

        :param request: Incoming webworks request.

        :returns: ``(bucket key, batches per window, authenticated)``.
    """
    principal = getattr(request, "auth_principal", None)
    user_id = getattr(principal, "user_id", None) if principal is not None else None
    if user_id is not None and len(str(user_id)) > 0:
        rtnval = ("user:{}".format(user_id), RATE_LIMIT_MAX_BATCHES_PER_USER, True)
        return rtnval
    rtnval = (ANONYMOUS_BUCKET_KEY, RATE_LIMIT_MAX_BATCHES, False)
    return rtnval


def _aggregate_entries(*, entries: List[Dict[str, Any]]) -> int:
    """
        Fold validated entries of the known shell metrics into the
        process registry. Unknown names, labels, and implausible values
        are ignored.

        :param entries: Validated beacon entries.

        :returns: Number of entries recorded.
    """
    recorded = 0
    for entry in entries:
        name = entry["metric"]
        value = float(entry["value"])
        if math.isfinite(value) is False or value < 0.0:
            continue
        histogram = UI_TIMING_HISTOGRAMS.get(name, None)
        if histogram is not None:
            if value <= MAX_UI_TIMING_SECONDS:
                histogram.observe(value=value)
                recorded += 1
            continue
        counter = UI_COUNTERS.get(name, None)
        if counter is not None and value <= MAX_UI_COUNTER_INCREMENT:
            counter.inc(labels=(), amount=value)
            recorded += 1
    rtnval = recorded
    return rtnval


def collect_ui_metric_families() -> List[MetricFamily]:
    """
        The aggregated shell metrics, for ``/metrics`` (registered as a
        collector by :func:`register_ui_metrics_routes`).

        :returns: One family per catalog metric.
    """
    pid = [("pid", str(os.getpid()))]
    families: List[MetricFamily] = []
    for histogram in UI_TIMING_HISTOGRAMS.values():
        families.append(histogram.collect(extra_labels=pid))
    for counter in UI_COUNTERS.values():
        families.append(counter.collect(extra_labels=pid))
    rtnval = families
    return rtnval


def _validate_entry(
        *,
        entry: Any,
        position: int
    ) -> Optional[str]:
    """
        Return None when ``entry`` is a well-formed measurement,
        or a short error string identifying the first malformed
        field. Validation is strict: a single bad entry rejects
        the whole batch (the client buffers in lock-step batches
        and a partial accept would mask bugs).

        :param entry: One element of the JSON array.
        :param position: Index within the array (for diagnostics).

        :returns: Error description or None.
    """
    if not isinstance(entry, dict):
        rtnval = "entry_{0}_not_object".format(position)
        return rtnval

    metric = entry.get("metric")
    if not isinstance(metric, str) or len(metric) == 0:
        rtnval = "entry_{0}_missing_metric".format(position)
        return rtnval
    if len(metric) > MAX_METRIC_NAME_LENGTH:
        rtnval = "entry_{0}_metric_too_long".format(position)
        return rtnval

    value = entry.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        rtnval = "entry_{0}_invalid_value".format(position)
        return rtnval

    timestamp_ms = entry.get("timestamp_ms")
    if not isinstance(timestamp_ms, (int, float)) or isinstance(
        timestamp_ms, bool
    ):
        rtnval = "entry_{0}_invalid_timestamp_ms".format(position)
        return rtnval

    labels = entry.get("labels", None)
    if labels is not None:
        if not isinstance(labels, dict):
            rtnval = "entry_{0}_labels_not_object".format(position)
            return rtnval
        if len(labels) > MAX_LABEL_COUNT:
            rtnval = "entry_{0}_too_many_labels".format(position)
            return rtnval
        for key, label_value in labels.items():
            if not isinstance(key, str) or len(key) == 0:
                rtnval = "entry_{0}_invalid_label_key".format(position)
                return rtnval
            if not isinstance(label_value, str):
                rtnval = "entry_{0}_invalid_label_value".format(position)
                return rtnval
            if (
                len(key) > MAX_LABEL_LENGTH
                or len(label_value) > MAX_LABEL_LENGTH
            ):
                rtnval = "entry_{0}_label_too_long".format(position)
                return rtnval

    rtnval = None
    return rtnval


def _parse_json_body(request: Request) -> Tuple[Optional[Any], Optional[str]]:
    """
        Parse the request body as JSON. Returns ``(payload, error)``
        where exactly one is non-None.

        :param request: Incoming webworks request.

        :returns: Tuple ``(payload, error_string)``.
    """
    parser = getattr(request, "json", None)
    if callable(parser):
        try:
            payload = parser()
            rtnval = (payload, None)
            return rtnval
        except Exception as parse_err:
            rtnval = (None, "invalid_json: {0}".format(parse_err))
            return rtnval

    body_attr = getattr(request, "body", None)
    if body_attr is None:
        rtnval = (None, "missing_body")
        return rtnval

    import json as _json

    try:
        if isinstance(body_attr, bytes):
            decoded = body_attr.decode("utf-8")
        else:
            decoded = str(body_attr)
        payload = _json.loads(decoded)
        rtnval = (payload, None)
        return rtnval
    except Exception as parse_err:
        rtnval = (None, "invalid_json: {0}".format(parse_err))
        return rtnval


def handle_ingest_ui_metrics(request: Request) -> Response:
    """
        ``POST /api/v1/_metrics/ui`` -- accept a batch of client
        measurements emitted by the site shell.

        The handler does *not* persist; it logs a compact summary
        and returns 204 on success. Rate-limit violations return
        429. Malformed payloads return 400 with an RFC 7807
        problem document.

        :param request: Incoming webworks request.

        :returns: Webworks response (204 / 400 / 429).
    """
    now = time.monotonic()
    bucket_key, limit, authenticated = _rate_limit_bucket(request=request)
    allowed = _RATE_LIMITER.check_and_record(address=bucket_key, now=now, limit=limit)
    if allowed is False:
        rtnval = problem_response_for_http_status(
            status=429,
            detail="Too many metric beacons; slow down.",
            instance=request.path,
        )
        return rtnval

    payload, parse_error = _parse_json_body(request=request)
    if parse_error is not None:
        rtnval = problem_response_for_http_status(
            status=400,
            detail=parse_error,
            instance=request.path,
        )
        return rtnval

    if not isinstance(payload, list):
        rtnval = problem_response_for_http_status(
            status=400,
            detail="payload_not_array",
            instance=request.path,
        )
        return rtnval

    if len(payload) > MAX_BATCH_SIZE:
        rtnval = problem_response_for_http_status(
            status=400,
            detail="batch_too_large",
            instance=request.path,
        )
        return rtnval

    for position, entry in enumerate(payload):
        validation_error = _validate_entry(entry=entry, position=position)
        if validation_error is not None:
            rtnval = problem_response_for_http_status(
                status=400,
                detail=validation_error,
                instance=request.path,
            )
            return rtnval

    metric_counts: Dict[str, int] = {}
    for entry in payload:
        metric_name = entry["metric"]
        previous = metric_counts.get(metric_name, 0)
        metric_counts[metric_name] = previous + 1

    # Only signed-in browsers feed the aggregates an operator alerts
    # on; anonymous batches are validated and acknowledged only.
    recorded = 0
    if authenticated is True:
        recorded = _aggregate_entries(entries=payload)

    _LOGGER.info(
        "pychestrate.ui.shell.metric_ingest count=%d distinct=%d recorded=%d client=%s",
        len(payload),
        len(metric_counts),
        recorded,
        bucket_key,
    )

    body: Dict[str, Any] = {
        "accepted": len(payload),
        "distinct_metrics": len(metric_counts),
        "recorded": recorded,
    }
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def register_ui_metrics_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the UI metrics ingest route to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    full_path = version_prefix + METRICS_PATH
    app.attach_route(full_path, methods=["POST"])(
        handle_ingest_ui_metrics
    )
    from ccai.pychestrate.webservice.system.operations import (  # noqa: E402
        register_metrics_collector,
    )
    register_metrics_collector(collector=collect_ui_metric_families)
    return


__all__ = [
    "METRICS_PATH",
    "MAX_BATCH_SIZE",
    "RATE_LIMIT_MAX_BATCHES",
    "RATE_LIMIT_MAX_BATCHES_PER_USER",
    "RATE_LIMIT_WINDOW_SECONDS",
    "UI_COUNTERS",
    "UI_TIMING_HISTOGRAMS",
    "collect_ui_metric_families",
    "register_ui_metrics_routes",
    "handle_ingest_ui_metrics",
]
