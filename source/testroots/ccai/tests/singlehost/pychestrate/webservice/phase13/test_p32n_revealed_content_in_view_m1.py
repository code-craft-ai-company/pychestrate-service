"""
.. module:: test_p32n_revealed_content_in_view_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Content a person opens is brought into view and given focus (ORC-41).

.. moduleauthor:: Code Craft AI LLC

Choosing "Show Published Release" on a long list of release channels, or
"Delivery History" on a long list of webhook subscriptions, rendered the detail
below the list, out of sight, with focus left on the button: nothing on the screen
changed and a keyboard user was told nothing. Forms that open above their list
never moved focus into the first field. ``shared/reveal.js`` now scrolls the
opened content into view (only when it is not already) and focuses it. The pages
are opened in a browser against stubbed API answers, with lists longer than the
window.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Any, Dict, List, Tuple

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 700}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
ONE_PROJECT = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}

#: Rows enough that the region below the list is out of a 700px window.
ROWS: int = 30


def _placement(page: Any, region_selector: str) -> Tuple[bool, bool, str]:
    """(region is fully inside the window, focus is inside the region, what has focus)."""
    return tuple(page.evaluate(
        """(selector) => {
            const region = document.querySelector(selector);
            const box = region.getBoundingClientRect();
            let active = document.activeElement;
            while (active && active.shadowRoot && active.shadowRoot.activeElement) { active = active.shadowRoot.activeElement; }
            const inside = region.contains(document.activeElement);
            const label = document.activeElement ? (document.activeElement.getAttribute('data-role') || document.activeElement.tagName.toLowerCase()) : '';
            return [box.top >= 0 && box.bottom <= window.innerHeight, inside, label];
        }""",
        region_selector,
    ))


def test_a_release_detail_opened_below_a_long_list_is_scrolled_to_and_focused(browser: Browser):
    """
    **Feature: revealed content in view (ORC-41)**
    **Property: choosing Show Published Release on the first row of a list longer than the
    window leaves the detail fully in view with focus inside it (on its heading).**
    """
    entries = [
        {
            "channel_id": "c{:03d}".format(number), "component": "pychestrate-client", "version": "1.0.{}".format(number),
            "channel": "stable", "status": "published", "rollout_fraction": 1.0, "artifact_uri": "s3://bucket/x{}".format(number),
            "artifact_sha256": "ab" * 32, "issued_by": "release-bot", "issued_at": "2026-09-{:02d}T10:00:00Z".format(1 + number % 28),
        }
        for number in range(ROWS)
    ]
    stubs: Dict[str, Any] = {"/api/v1/release-channels": {"items": entries, "meta": {"total": ROWS}}}
    for entry in entries:
        stubs["/api/v1/release-channels/" + entry["channel_id"]] = entry
    page = open_shell_page(browser, path="/release-channels", bundle_names=["pyc-site-shell", "pyc-ops-bundle"], api_stubs=stubs, **DESKTOP)
    try:
        page.wait_for_selector('[data-role="show-release"]')
        page.wait_for_timeout(800)
        page.locator('[data-role="show-release"]').first.click()
        page.wait_for_selector('[data-role="release-detail"]')
        page.wait_for_timeout(500)
        in_view, focused_inside, _label = _placement(page, '[data-role="detail-region"]')
        heading = page.evaluate("() => document.activeElement && document.activeElement.textContent.trim().slice(0, 18)")
    finally:
        page.context.close()

    testbase.assert_equal((in_view, focused_inside, heading), (True, True, "Published Release "))
    return


def test_a_delivery_history_opened_below_a_long_list_is_scrolled_to_and_focused(browser: Browser):
    """
    **Feature: revealed content in view (ORC-41)**
    **Property: choosing Delivery History on the first outbound subscription of a list longer
    than the window leaves the history fully in view with focus inside it.**
    """
    subscriptions = [
        {"subscription_id": "s{:03d}".format(number), "name": "hook-{}".format(number), "url": "https://hooks.example/{}".format(number), "topic_filters": [], "enabled": True}
        for number in range(ROWS)
    ]
    deliveries = {"items": [{"topic": "entity.run.failed", "outcome": "delivered", "response_status": 200, "response_excerpt": "ok", "attempted_at": "2026-09-29T10:00:00Z"}], "meta": {"total": 1}}
    stubs: Dict[str, Any] = {
        "/api/v1/projects": ONE_PROJECT,
        "/api/v1/webhooks/in/integrations": {"items": [], "meta": {"total": 0}},
        "/api/v1/webhooks/out/subscriptions": {"items": subscriptions, "meta": {"total": ROWS}},
    }
    for subscription in subscriptions:
        stubs["/api/v1/webhooks/out/subscriptions/{}/deliveries".format(subscription["subscription_id"])] = deliveries
    page = open_shell_page(browser, path="/webhooks?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-ops-bundle"], api_stubs=stubs, **DESKTOP)
    try:
        page.wait_for_selector('[data-role="tab-outbound"]')
        page.locator('[data-role="tab-outbound"]').click()
        page.wait_for_selector('[data-role="delivery-history"]')
        page.wait_for_timeout(800)
        page.locator('[data-role="delivery-history"]').first.click()
        page.wait_for_selector('[data-role="outbound-history-region"] mj-data-table')
        page.wait_for_timeout(500)
        in_view, focused_inside, _label = _placement(page, '[data-role="outbound-history-region"]')
    finally:
        page.context.close()

    testbase.assert_equal((in_view, focused_inside), (True, True))
    return


def test_a_form_that_opens_takes_focus_in_its_first_field(browser: Browser):
    """
    **Feature: revealed content in view (ORC-41)**
    **Property: choosing Create SLO opens the form and puts focus inside it (a keyboard user
    types into the form, not on the button that opened it); closing and opening again does the
    same.**
    """
    page = open_shell_page(
        browser, path="/slos?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={"/api/v1/projects": ONE_PROJECT, "/api/v1/me/permissions": {"permissions": ["system:slos.write"]}}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="create-toggle"]')
        page.wait_for_timeout(800)
        page.locator('[data-role="create-toggle"]').click()
        page.wait_for_selector('[data-role="create-form"]')
        page.wait_for_timeout(300)
        first = _placement(page, '[data-role="create-region"]')
        page.locator('[data-role="create-toggle"]').click()
        page.wait_for_timeout(200)
        page.locator('[data-role="create-toggle"]').click()
        page.wait_for_selector('[data-role="create-form"]')
        page.wait_for_timeout(300)
        second = _placement(page, '[data-role="create-region"]')
    finally:
        page.context.close()

    testbase.assert_equal((first[0], first[1], second[0], second[1]), (True, True, True, True))
    return


def test_every_form_toggle_in_the_bundles_hands_focus_to_the_form_it_opens():
    """
    **Feature: revealed content in view (ORC-41)**
    **Property: every bundle view method named ``_toggle_*_form`` / ``_toggle_evaluate_panel``
    that opens content calls ``reveal`` (so a new form cannot open without moving focus).**
    """
    root = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir,
        "site", "ccai", "pychestrate", "webservice", "webinterface", "static", "javascript",
    )
    missing: List[str] = []
    seen = 0
    for path in glob.glob(os.path.join(root, "pyc-*-bundle", "*-view.js")):
        source = open(path, encoding="utf-8").read()
        for match in re.finditer(r"\n  _toggle_(?:[a-z]+_form|evaluate_panel)\([^)]*\) \{\n(.*?)\n  \}\n", source, re.S):
            seen += 1
            if "reveal(" not in match.group(1):
                missing.append(os.path.relpath(path, root) + ": " + match.group(0).split("(")[0].strip())

    testbase.assert_equal((missing, seen >= 10), ([], True))
    return
