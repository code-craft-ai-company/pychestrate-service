"""
.. module:: test_p17g_ui_metrics_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native ``POST /api/v1/_metrics/ui``
               endpoint introduced in PR p17g (M3 site shell
               hardening).

.. moduleauthor:: Code Craft AI LLC

The endpoint is the server-side landing pad for the client-side
metrics beacon emitted by ``<pyc-site-shell>``. PR p17g ships
the endpoint as a stub: validate the payload shape, rate-limit
per remote address, log a one-line summary, return 200 with the
accepted count. Persistence and Prometheus exposition are a
follow-on concern.

Tests cover:

* Happy path -- a well-formed batch returns 200 with the
  accepted-count summary.
* Malformed payload -- non-array body, missing ``metric`` key,
  invalid ``value``, oversized batch, all return 400.
* Rate limiting -- the 13th batch from a single address inside
  the 60-second window returns 429.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.metrics.restapi.v1 import (
    ui_metrics_routes,
)


class _FakeRequest:
    """
        Minimal duck-typed webworks Request for the ingest
        handler. Only ``path``, ``body``, and ``remote_address``
        are touched.
    """

    def __init__(
            self,
            *,
            path: str = "/api/v1/_metrics/ui",
            body: Optional[bytes] = None,
            remote_address: str = "192.0.2.1"
        ) -> None:
        self.path: str = path
        self.body: Optional[bytes] = body
        self.remote_address: str = remote_address
        return


def _decode_body(response: Any) -> Dict[str, Any]:
    """
        Pull the JSON body off a webworks response for assertion.
    """
    body_bytes = response.body
    if isinstance(body_bytes, (bytes, bytearray)):
        text = body_bytes.decode("utf-8")
    else:
        text = str(body_bytes)
    rtnval = json.loads(text)
    return rtnval


def _reset_rate_limiter() -> None:
    """
        Wipe the module-level limiter between tests so cases do
        not bleed into each other.
    """
    ui_metrics_routes._RATE_LIMITER._buckets.clear()
    return


def test_happy_path_returns_200_with_summary() -> None:
    """
        A well-formed batch returns 200 and an accepted-count
        summary; the response is a webworks JSONResponse.
    """
    _reset_rate_limiter()
    batch = [
        {
            "metric": "pychestrate_ui_shell_tti_seconds",
            "value": 0.187,
            "labels": {"route": "/admin/users"},
            "timestamp_ms": 1710000000000,
        },
        {
            "metric": "pychestrate_ui_shell_sidebar_render_duration_seconds",
            "value": 0.004,
            "labels": None,
            "timestamp_ms": 1710000000050,
        },
    ]
    request = _FakeRequest(body=json.dumps(batch).encode("utf-8"))
    response = ui_metrics_routes.handle_ingest_ui_metrics(request)
    testbase.assert_equal(isinstance(response, JSONResponse), True)
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["accepted"], 2)
    testbase.assert_equal(body["distinct_metrics"], 2)
    return


def test_non_array_payload_returns_400() -> None:
    """
        A payload that is not a JSON array yields HTTP 400.
    """
    _reset_rate_limiter()
    request = _FakeRequest(body=b'{"metric": "x", "value": 1.0}')
    response = ui_metrics_routes.handle_ingest_ui_metrics(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_missing_metric_key_returns_400() -> None:
    """
        An entry missing the required ``metric`` field yields
        HTTP 400 identifying the offending position.
    """
    _reset_rate_limiter()
    batch = [{"value": 1.0, "timestamp_ms": 1710000000000}]
    request = _FakeRequest(body=json.dumps(batch).encode("utf-8"))
    response = ui_metrics_routes.handle_ingest_ui_metrics(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_invalid_value_returns_400() -> None:
    """
        An entry whose ``value`` is a string is rejected.
    """
    _reset_rate_limiter()
    batch = [
        {
            "metric": "x",
            "value": "not a number",
            "timestamp_ms": 1710000000000,
        }
    ]
    request = _FakeRequest(body=json.dumps(batch).encode("utf-8"))
    response = ui_metrics_routes.handle_ingest_ui_metrics(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_oversized_batch_returns_400() -> None:
    """
        A batch larger than ``MAX_BATCH_SIZE`` is rejected.
    """
    _reset_rate_limiter()
    oversize_count = ui_metrics_routes.MAX_BATCH_SIZE + 1
    batch: List[Dict[str, Any]] = []
    for index in range(oversize_count):
        batch.append(
            {
                "metric": "x",
                "value": 0.0,
                "timestamp_ms": 1710000000000 + index,
            }
        )
    request = _FakeRequest(body=json.dumps(batch).encode("utf-8"))
    response = ui_metrics_routes.handle_ingest_ui_metrics(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_rate_limit_returns_429_after_threshold() -> None:
    """
        More than ``RATE_LIMIT_MAX_BATCHES`` requests from a
        single address inside the window return HTTP 429.
    """
    _reset_rate_limiter()
    batch = [
        {
            "metric": "x",
            "value": 0.0,
            "timestamp_ms": 1710000000000,
        }
    ]
    body = json.dumps(batch).encode("utf-8")
    last_response = None
    for _ in range(ui_metrics_routes.RATE_LIMIT_MAX_BATCHES):
        request = _FakeRequest(body=body)
        last_response = ui_metrics_routes.handle_ingest_ui_metrics(
            request
        )
    testbase.assert_equal(last_response.status_code, 200)
    request = _FakeRequest(body=body)
    limited_response = ui_metrics_routes.handle_ingest_ui_metrics(
        request
    )
    testbase.assert_equal(limited_response.status_code, 429)
    return


__all__ = [
    "test_happy_path_returns_200_with_summary",
    "test_non_array_payload_returns_400",
    "test_missing_metric_key_returns_400",
    "test_invalid_value_returns_400",
    "test_oversized_batch_returns_400",
    "test_rate_limit_returns_429_after_threshold",
]
