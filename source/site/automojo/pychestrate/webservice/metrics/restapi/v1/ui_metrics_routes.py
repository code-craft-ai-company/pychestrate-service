"""
.. module:: metrics.restapi.v1.ui_metrics_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST route for ``POST /api/v1/_metrics/ui``.

.. moduleauthor:: Automation Mojo LLC

The site shell (9-site-shell) beacons client-side measurement
batches to this endpoint via ``navigator.sendBeacon``. PR p17g
ships the endpoint as a *stub* -- the payload is validated,
rate-limited cheaply, and logged. No persistent storage. A full
metrics-aggregation backend (Prometheus exposition, time-series
bucketing) is a separate concern tracked in
``9-site-shell/tasks.md``.

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

Malformed payloads return 400. Excess requests from a single
remote address return 429.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import time

from typing import Any, Dict, List, Optional, Tuple

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
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

#: Rate limit window (seconds) per remote address.
RATE_LIMIT_WINDOW_SECONDS = 60

#: Maximum batches per remote address per window. The client emits
#: at most one batch per ~30s under steady-state usage, so 12
#: gives ~6x headroom for navigation bursts.
RATE_LIMIT_MAX_BATCHES = 12

_LOGGER = logging.getLogger("pychestrate.ui.shell.metrics")


class _RateLimiter:
    """
        In-process sliding-window rate limiter keyed by remote
        address. Cheap -- a single dict + list per address.

        Not durable across processes; mirrored per gunicorn worker.
        Adequate for an informational beacon endpoint -- the
        per-worker cap is multiplied by worker-count in practice.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, List[float]] = {}
        return

    def check_and_record(self, *, address: str, now: float) -> bool:
        """
            Return True when the supplied address is under the
            limit and the current request should be counted.

            :param address: Remote address (or "unknown" sentinel).
            :param now: Monotonic-ish timestamp (seconds).

            :returns: True if allowed; False if the limit is hit.
        """
        bucket = self._buckets.get(address)
        if bucket is None:
            bucket = []
            self._buckets[address] = bucket

        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        retained: List[float] = []
        for timestamp in bucket:
            if timestamp >= cutoff:
                retained.append(timestamp)

        if len(retained) >= RATE_LIMIT_MAX_BATCHES:
            self._buckets[address] = retained
            rtnval = False
            return rtnval

        retained.append(now)
        self._buckets[address] = retained
        rtnval = True
        return rtnval


_RATE_LIMITER = _RateLimiter()


def _resolve_remote_address(request: Request) -> str:
    """
        Resolve the remote address for rate-limit bucketing.

        Falls back to ``"unknown"`` when no address attribute is
        present on the request -- which keeps the bucket key
        well-defined even under unit-test stubs.

        :param request: Incoming webworks request.

        :returns: Address string (never None).
    """
    candidate = getattr(request, "remote_address", None)
    if isinstance(candidate, str) and len(candidate) > 0:
        rtnval = candidate
        return rtnval

    client_addr = getattr(request, "client", None)
    if client_addr is not None:
        host_attr = getattr(client_addr, "host", None)
        if isinstance(host_attr, str) and len(host_attr) > 0:
            rtnval = host_attr
            return rtnval

    rtnval = "unknown"
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
    address = _resolve_remote_address(request=request)
    allowed = _RATE_LIMITER.check_and_record(address=address, now=now)
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

    _LOGGER.info(
        "pychestrate.ui.shell.metric_ingest count=%d distinct=%d address=%s",
        len(payload),
        len(metric_counts),
        address,
    )

    body: Dict[str, Any] = {
        "accepted": len(payload),
        "distinct_metrics": len(metric_counts),
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
    return


__all__ = [
    "METRICS_PATH",
    "MAX_BATCH_SIZE",
    "RATE_LIMIT_MAX_BATCHES",
    "RATE_LIMIT_WINDOW_SECONDS",
    "register_ui_metrics_routes",
    "handle_ingest_ui_metrics",
]
