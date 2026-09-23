"""
.. module:: test_platform_ui_metrics_beacon_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the UI-metrics beacon budget and
               aggregation (audit LD-03).

.. moduleauthor:: Code Craft AI LLC

The beacon was capped at 12 batches a minute keyed on
``request.remote_address`` -- an attribute webworks requests do not
have -- so every client shared one bucket, and a normal-speed sweep
drew 429s on 34 of 62 pages. The payload was only logged. These tests
pin:

* each signed-in user has an own budget sized for page-view rates;
* anonymous traffic shares one bucket and cannot use up a user's;
* a spoofed forwarding header does not buy an anonymous caller a new
  bucket;
* signed-in batches of the known shell metrics are aggregated (and
  show up on /metrics); unknown names, anonymous batches and
  implausible values are not.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase

from ccai.pychestrate.webservice.metrics.restapi.v1 import ui_metrics_routes
from ccai.pychestrate.webservice.system import operations, prometheus


class _Principal:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        return


class _Headers:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values = values or {}
        return

    def get(self, name: str, default: Any = None) -> Any:
        rtnval = self._values.get(name, default)
        return rtnval


class _FakeRequest:
    def __init__(
            self,
            *,
            entries: List[Dict[str, Any]],
            user_id: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None
        ) -> None:
        self.path = "/api/v1/_metrics/ui"
        self.body = json.dumps(entries).encode("utf-8")
        self.auth_principal = _Principal(user_id) if user_id is not None else None
        self.headers = _Headers(headers)
        return


def _entry(metric: str = "pychestrate_ui_shell_tti_seconds", value: float = 0.2) -> Dict[str, Any]:
    rtnval = {"metric": metric, "value": value, "labels": {"route": "/admin/users"}, "timestamp_ms": 1710000000000}
    return rtnval


def _reset() -> None:
    ui_metrics_routes._RATE_LIMITER._buckets.clear()
    for histogram in ui_metrics_routes.UI_TIMING_HISTOGRAMS.values():
        histogram.reset_for_testing()
    for counter in ui_metrics_routes.UI_COUNTERS.values():
        counter.reset_for_testing()
    return


def _send(request: _FakeRequest) -> Any:
    rtnval = ui_metrics_routes.handle_ingest_ui_metrics(request)
    return rtnval


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_one_page_view_per_second_for_a_minute_is_never_limited():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: a signed-in user sending one batch per page view at one
    page a second for a full minute gets no 429.**
    """
    _reset()
    statuses = [_send(_FakeRequest(entries=[_entry()], user_id="u-1")).status_code for _ in range(60)]
    testbase.assert_equal(sorted(set(statuses)), [200])
    return


def test_users_have_separate_budgets():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: after user A exhausts their budget, user B is still
    accepted.**
    """
    _reset()
    for _ in range(ui_metrics_routes.RATE_LIMIT_MAX_BATCHES_PER_USER):
        _send(_FakeRequest(entries=[_entry()], user_id="user-a"))
    a_again = _send(_FakeRequest(entries=[_entry()], user_id="user-a")).status_code
    b_first = _send(_FakeRequest(entries=[_entry()], user_id="user-b")).status_code
    testbase.assert_equal((a_again, b_first), (429, 200))
    return


def test_anonymous_traffic_cannot_use_up_a_users_budget():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: exhausting the shared anonymous bucket leaves signed-in
    users unaffected.**
    """
    _reset()
    for _ in range(ui_metrics_routes.RATE_LIMIT_MAX_BATCHES + 5):
        _send(_FakeRequest(entries=[_entry()]))
    status = _send(_FakeRequest(entries=[_entry()], user_id="u-1")).status_code
    testbase.assert_equal(status, 200)
    return


def test_forwarding_headers_do_not_create_new_anonymous_buckets():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: anonymous callers share one bucket whatever
    X-Forwarded-For / X-Real-IP they send.**
    """
    _reset()
    for index in range(ui_metrics_routes.RATE_LIMIT_MAX_BATCHES):
        _send(_FakeRequest(entries=[_entry()], headers={"X-Forwarded-For": "10.0.0.{}".format(index),
                                                       "X-Real-Ip": "10.0.1.{}".format(index)}))
    status = _send(_FakeRequest(entries=[_entry()], headers={"X-Forwarded-For": "203.0.113.9"})).status_code
    testbase.assert_equal(status, 429)
    return


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_signed_in_timings_are_aggregated():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: a signed-in batch of a known timing metric is recorded
    in its histogram and reported as recorded.**
    """
    _reset()
    response = _send(_FakeRequest(entries=[_entry(value=0.3), _entry(value=1.2)], user_id="u-1"))
    body = json.loads(response.body.decode("utf-8"))
    histogram = ui_metrics_routes.UI_TIMING_HISTOGRAMS["pychestrate_ui_shell_tti_seconds"]
    testbase.assert_equal((body["recorded"], histogram.count()), (2, 2.0))
    return


def test_anonymous_batches_are_not_aggregated():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: an anonymous batch is acknowledged but feeds no
    aggregate.**
    """
    _reset()
    response = _send(_FakeRequest(entries=[_entry()]))
    body = json.loads(response.body.decode("utf-8"))
    histogram = ui_metrics_routes.UI_TIMING_HISTOGRAMS["pychestrate_ui_shell_tti_seconds"]
    testbase.assert_equal((response.status_code, body["recorded"], histogram.count()), (200, 0, 0.0))
    return


def test_unknown_names_and_implausible_values_are_not_aggregated():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: unknown metric names, negative values and timings past
    the plausibility cap are dropped from the aggregates.**
    """
    _reset()
    response = _send(_FakeRequest(entries=[
        _entry(metric="attacker_metric_name", value=1.0),
        _entry(value=-1.0),
        _entry(value=10_000.0),
    ], user_id="u-1"))
    body = json.loads(response.body.decode("utf-8"))
    testbase.assert_equal(body["recorded"], 0)
    return


def test_click_counter_is_aggregated():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: the sidebar-click counter adds the reported amount.**
    """
    _reset()
    _send(_FakeRequest(entries=[_entry(metric="pychestrate_ui_shell_sidebar_entry_clicked_total", value=3)],
                       user_id="u-1"))
    counter = ui_metrics_routes.UI_COUNTERS["pychestrate_ui_shell_sidebar_entry_clicked_total"]
    testbase.assert_equal(counter.value(labels=()), 3.0)
    return


def test_aggregates_are_exposed_on_metrics():
    """
    **Feature: UI metrics beacon (LD-03)**
    **Property: registering the beacon route registers its collector,
    so /metrics renders the pychestrate_ui_shell_tti_seconds
    histogram.**
    """
    class _App:
        def attach_route(self, path: str, methods: Optional[List[str]] = None) -> Any:
            return lambda func: func

    _reset()
    ui_metrics_routes.register_ui_metrics_routes(app=_App(), version_prefix="/api/v1")
    _send(_FakeRequest(entries=[_entry(value=0.4)], user_id="u-1"))
    families = []
    for collector in operations._EXTRA_COLLECTORS:
        families.extend(collector())
    text = prometheus.render_exposition(families=families)
    testbase.assert_true("pychestrate_ui_shell_tti_seconds_count{pid=" in text, text[:500])
    return
