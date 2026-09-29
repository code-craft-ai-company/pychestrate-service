"""
.. module:: test_p31z_health_check_queue_and_dashboard_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Run Health Check queues the check instead of probing in
               the web request, and the health dashboard is paged
               (RES-39).

.. moduleauthor:: Code Craft AI LLC

A probe that took four seconds held the request for four seconds, and a
few slow devices could use up the server's threads. "Run Health Check"
now queues the check and returns at once; the housekeeping worker runs it
ahead of the scheduled ones, and the health page shows the outcome, with
the reason when it failed. A queued check the worker has not picked up
for two minutes is flagged. The dashboard loaded a thousand resources to
fill four tables and cut each group off with no way to see the rest: it
now loads twenty per group, says how many there are, and "View all" opens
one status a page at a time.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import time
import uuid

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.health_monitor import HealthMonitor, ProbeFailedError
from ccai.pychestrate.core.orm import HealthCheckConfig, Resource

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    open_db_session,
    post_form,
)


PROBE_URL = "http://10.0.4.21/health"
SLOW_PROBE_SECONDS = 1.5


def _name(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def _monitored_device(cookies: Dict[str, str], *, enabled: bool = True) -> str:
    """A device with a health check configured; returns its id."""
    created = post_form(
        path="/resources/create",
        fields={"name": _name("hq"), "resource_type": "device", "pool_id": "", "description": "",
                "capacity": "1", "metadata": "{}"},
        cookies=cookies,
    )
    match = re.search(r"/resources/(\d+)", created.header("Location") or "")
    testbase.assert_true(match is not None, "device not created: {}".format(created.status_code))
    resource_id = match.group(1)
    fields = {"probe_url": PROBE_URL, "interval_seconds": "3600", "timeout_seconds": "5",
              "failure_threshold": "3", "success_threshold": "1"}
    if enabled:
        fields["enabled"] = "on"
    configured = post_form(path="/resources/health/{}/config".format(resource_id), fields=fields, cookies=cookies)
    testbase.assert_equal(configured.status_code, 303, "health check not configured")
    return resource_id


class _SlowProbe:
    """
        Stands in for the device probe: waits ``seconds`` (a slow device),
        then passes or fails with ``reason``. Remembers every call.
    """

    def __init__(self, *, seconds: float = 0.0, reason: Optional[str] = None) -> None:
        self.seconds: float = seconds
        self.reason: Optional[str] = reason
        self.calls: List[str] = []
        self._original: Any = None
        return

    def __enter__(self) -> "_SlowProbe":
        self._original = HealthMonitor._execute_url_probe
        probe = self

        def _probe(monitor: Any, url: str, timeout_seconds: int) -> bool:
            probe.calls.append(url)
            time.sleep(probe.seconds)
            if probe.reason is not None:
                raise ProbeFailedError(probe.reason)
            return True

        HealthMonitor._execute_url_probe = _probe
        return self

    def __exit__(self, *exc_info: Any) -> None:
        HealthMonitor._execute_url_probe = self._original
        return


def _work_the_queue(resource_id: str) -> None:
    """Do what the housekeeping worker does for one resource."""
    db_session = open_db_session()
    try:
        HealthMonitor(db_session=db_session).run_health_check(int(resource_id))
    finally:
        db_session.close()
    return


def _request_check(resource_id: str, cookies: Dict[str, str]) -> Tuple[Any, float, str]:
    """POST Run Health Check; returns ``(response, seconds it took, the page it lands on)``."""
    started = time.monotonic()
    response = post_form(path="/resources/health/{}/check".format(resource_id), fields={}, cookies=cookies)
    took = time.monotonic() - started
    landed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    return (response, took, html.unescape(landed.text))


def _detail(resource_id: str, cookies: Dict[str, str]) -> str:
    return html.unescape(get(path="/resources/health/{}".format(resource_id), cookies=cookies).text)


def _text_of(page: str, role: str) -> str:
    match = re.search(r'data-role="' + re.escape(role) + r'"[^>]*>(.*?)</(?:span|div|td)>', page, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip() if match is not None else ""


def test_run_health_check_returns_at_once_even_when_the_device_is_slow():
    """
    **Feature: queued health checks (RES-39)**
    **Property: with a device that takes over a second to answer, the
    Run Health Check request comes back in well under that, without
    having probed anything, saying the check is queued; the health page
    shows it waiting.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin)
    with _SlowProbe(seconds=SLOW_PROBE_SECONDS) as probe:
        response, took, landed = _request_check(resource_id, admin)

    testbase.assert_equal(
        (response.status_code, took < SLOW_PROBE_SECONDS / 2, probe.calls,
         "Health check queued." in landed, 'data-role="queued-check"' in landed),
        (303, True, [], True, True),
    )
    return


def test_asking_again_while_a_check_is_queued_says_so():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a second Run Health Check for the same device says one is
    already queued, and probes nothing.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin)
    with _SlowProbe() as probe:
        _request_check(resource_id, admin)
        _response, _took, landed = _request_check(resource_id, admin)

    testbase.assert_equal(
        ("already queued" in landed, "Health check queued." in landed, probe.calls),
        (True, False, []),
    )
    return


def test_the_worker_runs_the_check_and_the_page_shows_a_pass():
    """
    **Feature: queued health checks (RES-39)**
    **Property: once the worker has run the queued check, the health page
    shows the time and a "Passed" result and no longer shows a queued
    check.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin)
    before = _detail(resource_id, admin)
    with _SlowProbe() as probe:
        _request_check(resource_id, admin)
        _work_the_queue(resource_id)
    after = _detail(resource_id, admin)

    testbase.assert_equal(
        ("Not checked yet" in before, len(probe.calls), _text_of(after, "last-check-result"),
         'data-role="queued-check"' in after, "Not checked yet" in after),
        (True, 1, "Passed", False, False),
    )
    return


def test_a_failed_check_shows_why_on_the_health_page():
    """
    **Feature: queued health checks (RES-39)**
    **Property: when the queued check fails, the page shows "Failed" and
    the reason the device gave, kept after the request that started it.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin)
    with _SlowProbe(reason="The device answered with HTTP status 503.") as probe:
        _request_check(resource_id, admin)
        _work_the_queue(resource_id)
    after = _detail(resource_id, admin)

    testbase.assert_equal(
        (len(probe.calls), _text_of(after, "last-check-result"), _text_of(after, "last-check-message"),
         'data-role="queued-check"' in after),
        (1, "Failed", "The device answered with HTTP status 503.", False),
    )
    return


def test_a_check_that_is_switched_off_is_refused_with_advice():
    """
    **Feature: queued health checks (RES-39)**
    **Property: Run Health Check on a device whose check is disabled
    says to enable it under Configure Health Check and queues nothing.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin, enabled=False)
    _response, _took, landed = _request_check(resource_id, admin)
    page = _detail(resource_id, admin)

    testbase.assert_equal(
        ("switched off for this resource" in landed, "Configure Health Check" in landed,
         'data-role="queued-check"' in page),
        (True, True, False),
    )
    return


def test_a_device_with_no_health_check_is_told_to_configure_one():
    """
    **Feature: queued health checks (RES-39)**
    **Property: Run Health Check on a device with no health check
    configured says so, rather than queueing or failing with a raw
    error.**
    """
    admin = admin_cookies()
    created = post_form(
        path="/resources/create",
        fields={"name": _name("hqnone"), "resource_type": "device", "pool_id": "", "description": "",
                "capacity": "1", "metadata": "{}"},
        cookies=admin,
    )
    resource_id = re.search(r"/resources/(\d+)", created.header("Location") or "").group(1)
    _response, _took, landed = _request_check(resource_id, admin)

    testbase.assert_equal(("no health check yet" in landed, "queued" in landed), (True, False))
    return


def test_a_request_the_worker_has_not_picked_up_is_flagged():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a check that has waited ten minutes is flagged as waiting
    longer than expected and points at the housekeeping worker; one that
    has just been queued is not.**
    """
    admin = admin_cookies()
    resource_id = _monitored_device(admin)
    with _SlowProbe():
        _request_check(resource_id, admin)
    fresh = _detail(resource_id, admin)
    db_session = open_db_session()
    try:
        row = db_session.query(HealthCheckConfig).filter(HealthCheckConfig.resource_id == int(resource_id)).one()
        row.check_requested_at = utc_now() - timedelta(minutes=10)
        db_session.commit()
    finally:
        db_session.close()
    stale = _detail(resource_id, admin)

    testbase.assert_equal(
        ('data-role="queued-check-stale"' in fresh, 'data-role="queued-check-stale"' in stale,
         "housekeeping worker" in stale),
        (False, True, True),
    )
    return


def _offline_devices(count: int) -> Tuple[str, List[str]]:
    """
        ``count`` offline devices whose names sort in the order made, under
        a prefix no other test uses. Returns ``(prefix, names)``.
    """
    prefix = "dash" + uuid.uuid4().hex[:6]
    names = ["{}-{:03d}".format(prefix, index) for index in range(count)]
    db_session = open_db_session()
    try:
        for name in names:
            db_session.add(Resource(name=name, resource_type="device", capacity=1, health_status="offline",
                                    metadata_json={}, sensitive_fields=[]))
        db_session.commit()
    finally:
        db_session.close()
    return (prefix, names)


def _overview_card(page: str, title: str) -> str:
    for chunk in page.split('<div class="card">'):
        if title in chunk:
            return chunk
    return ""


def _listed(page: str, prefix: str) -> List[str]:
    return re.findall(r">(" + re.escape(prefix) + r"-\d+)</a></td>", page)


def test_the_overview_shows_twenty_a_group_and_links_to_the_rest():
    """
    **Feature: health dashboard paging (RES-39)**
    **Property: with more than twenty offline devices, the overview's
    offline table has at most twenty rows, says how many there are, and
    links to "View all"; the offline stat card still counts all of them.**
    """
    prefix, _names = _offline_devices(23)
    page = html.unescape(get(path="/resources/health", cookies=admin_cookies()).text)
    card = _overview_card(page, "Offline Resources")
    rows = re.findall(r'<td><a href="/resources/health/\d+">', card)
    total = int(re.search(r"Showing 20 of (\d+) resources", card).group(1)) if "Showing 20 of" in card else 0
    stat = re.search(r'<div class="stat-value">(\d+)</div>\s*<div class="stat-label">Offline</div>', page)

    testbase.assert_equal(
        (len(rows), total >= 23, 'data-role="view-all-offline"' in card, stat is not None and int(stat.group(1)) == total),
        (20, True, True, True),
    )
    return


def test_view_all_pages_through_one_status_without_repeating_or_skipping():
    """
    **Feature: health dashboard paging (RES-39)**
    **Property: opening one status with ten a page lists every one of the
    devices made, each once and in name order, across the pages; the
    pager's Next link keeps the status and the page size; only that
    status's table is shown.**
    """
    prefix, names = _offline_devices(23)
    admin = admin_cookies()
    seen: List[str] = []
    page_number = 1
    first_page = ""
    next_link = ""
    while True:
        page = html.unescape(get(path="/resources/health", cookies=admin,
                                 query={"status": "offline", "per_page": "10", "page": str(page_number)}).text)
        if page_number == 1:
            first_page = page
            found = re.search(r'<a href="([^"]*)" rel="next"', page)
            next_link = found.group(1) if found is not None else ""
        seen.extend(_listed(page, prefix))
        if 'rel="next"' not in page:
            break
        page_number = page_number + 1
        testbase.assert_true(page_number < 200, "the pager never ends")

    testbase.assert_equal(
        (seen, "status=offline" in next_link and "per_page=10" in next_link,
         "Online Resources" in first_page, 'data-role="all-statuses"' in first_page),
        (names, True, False, True),
    )
    return


def test_an_unknown_status_shows_the_overview_and_a_short_group_has_no_view_all():
    """
    **Feature: health dashboard paging (RES-39)**
    **Property: a status that is not one of the four falls back to the
    overview instead of failing; a group that fits in the overview has no
    "View all" link.**
    """
    admin = admin_cookies()
    response = get(path="/resources/health", cookies=admin, query={"status": "bogus"})
    page = html.unescape(response.text)
    maintenance = _overview_card(page, "Resources in Maintenance")

    testbase.assert_equal(
        (response.status_code, "Online Resources" in page, 'data-role="all-statuses"' in page,
         'data-role="view-all-maintenance"' in maintenance),
        (200, True, False, False),
    )
    return
