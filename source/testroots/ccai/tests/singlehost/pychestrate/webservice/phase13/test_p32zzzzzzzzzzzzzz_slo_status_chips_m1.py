"""
.. module:: test_p32zzzzzzzzzzzzzz_slo_status_chips_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The SLO list shows each objective's status when it opens, and an objective with no data is not green (ORC-36).

.. moduleauthor:: Code Craft AI LLC

The audit reported that an SLO's status loads per row on click and that "Breaching" is a grey chip. The list
endpoint already returns every objective's status, so the page shows them on opening without a request per row (the
row button only re-reads one); "Breaching" is red. But an objective with **no data in the window** was drawn green,
claiming health nobody measured; it is now neutral. The page is opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import json
import re

from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 700}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"


def _status(achieved: Optional[float], remaining: Optional[float], breaching: bool) -> Dict[str, Any]:
    return {
        "slo_id": "x", "achieved_ratio": achieved, "error_budget_remaining_ratio": remaining, "target": 0.99,
        "window_start": "2026-09-24T00:00:00Z", "window_end": "2026-10-01T00:00:00Z", "good_count": 1, "total_count": 2,
        "breaching": breaching, "reason": "r",
    }


def _slo(number: int, name: str, status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "slo_id": "5a5a5a5a-0000-4000-8000-00000000000{}".format(number), "project_id": PROJECT_ID, "name": name, "description": "",
        "kind": "availability_ratio", "target": 0.99, "window_seconds": 604800, "definition_config": {},
        "default_notification_route_key": None, "auto_attach_burn_rate_alerts": False, "version": 1,
        "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z", "status": status,
    }


ITEMS: List[Dict[str, Any]] = [
    _slo(1, "healthy", _status(0.999, 0.9, False)),
    _slo(2, "low budget", _status(0.991, 0.1, False)),
    _slo(3, "breaching", _status(0.9, 0.0, True)),
    _slo(4, "no data", _status(None, None, False)),
    _slo(5, "never evaluated", None),
]


def _open(browser: Browser) -> Any:
    requested: List[str] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": ["system:slos.write"]},
        },
    )
    context.route(
        re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/slos(\?.*)?$"),
        lambda route: route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": ITEMS, "meta": {"total": len(ITEMS)}})),
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.on("request", lambda request: requested.append(request.url[len(FAKE_ORIGIN):].split("?")[0]) if "/api/v1/" in request.url and "/slos" in request.url else None)
    page.goto(FAKE_ORIGIN + "/slos?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="create-toggle"]', state="attached")
    page.wait_for_timeout(1500)
    page.requested = requested
    return page


def test_statuses_are_shown_when_the_list_opens_without_a_request_per_row(browser: Browser):
    """
    **Feature: SLO status chips (ORC-36)**
    **Property: opening the SLO list shows every objective's status (the list answer carries it) with one request
    for the list and none per objective; an objective with no status at all reads "Not evaluated".**
    """
    page = _open(browser)
    try:
        chips = page.evaluate("""() => [...document.querySelector('mj-data-table').shadowRoot.querySelectorAll('[data-role=burn-indicator]')].map((el) => el.textContent)""")
        requested = list(page.requested)
    finally:
        page.context.close()

    testbase.assert_equal(
        (chips, requested),
        (["99.9% achieved", "99.1% achieved", "Breaching", "No data in window", "Not evaluated"], ["/api/v1/projects/{}/slos".format(PROJECT_ID)]),
    )
    return


def test_each_status_has_its_own_tone_and_no_data_is_not_green(browser: Browser):
    """
    **Feature: SLO status chips (ORC-36)**
    **Property: healthy is ok (green), a nearly spent budget warn, breaching error (red), and both "No data in
    window" and "Not evaluated" neutral: nothing measured is not reported as healthy.**
    """
    page = _open(browser)
    try:
        tones = page.evaluate("""() => [...document.querySelector('mj-data-table').shadowRoot.querySelectorAll('[data-role=burn-indicator]')].map((el) => el.getAttribute('data-tone'))""")
    finally:
        page.context.close()

    testbase.assert_equal(tones, ["ok", "warn", "error", "neutral", "neutral"])
    return


def test_a_chip_fits_its_column_and_stays_clear_of_the_row_buttons(browser: Browser):
    """
    **Feature: SLO status chips (ORC-36)**
    **Property: the longest chip ("No data in window") ends before the first row button starts, with room between
    (the Achieved column is wide enough for it).**
    """
    page = _open(browser)
    try:
        gap = page.evaluate("""() => {
            const root = document.querySelector('mj-data-table').shadowRoot;
            const chips = [...root.querySelectorAll('[data-role=burn-indicator]')];
            const chip = chips.find((el) => el.textContent === 'No data in window');
            const row_button = root.querySelector('[data-role=load-status]');
            return Math.round(row_button.getBoundingClientRect().left - chip.getBoundingClientRect().right);
        }""")
    finally:
        page.context.close()

    testbase.assert_equal(gap >= 8, True)
    return


#: Reads the colour a screenshot of a chip has just inside its left edge (the chip's own background, clear of its text).
_SAMPLE_JS: str = """async (b64) => {
  const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
  const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height;
  const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
  const d = ctx.getImageData(Math.min(4, img.width - 1), Math.floor(img.height / 2), 1, 1).data;
  return [d[0], d[1], d[2]];
}"""


def _family(rgb: List[int]) -> str:
    red, green, blue = rgb
    if red - green >= 15 and red - blue >= 15:
        return "red"
    if green - red >= 10 and green - blue >= 5:
        return "green"
    if red - blue >= 20:
        return "amber"
    if max(rgb) - min(rgb) <= 8:
        return "grey"
    return "other"


def test_breaching_is_drawn_red_and_no_data_grey_as_the_eye_sees_them(browser: Browser):
    """
    **Feature: SLO status chips (ORC-36)**
    **Property: measured from screenshots of the chips, not from their attributes: healthy is green, a nearly
    spent budget amber, "Breaching" red (the audit saw it grey), and "No data in window" and "Not evaluated" grey.**
    """
    page = _open(browser)
    reader = page.context.new_page()
    try:
        families = []
        for index in range(len(ITEMS)):
            png = page.locator('[data-role="burn-indicator"]').nth(index).screenshot()
            families.append(_family(reader.evaluate(_SAMPLE_JS, base64.b64encode(png).decode("ascii"))))
    finally:
        page.context.close()

    testbase.assert_equal(families, ["green", "amber", "red", "grey", "grey"])
    return
