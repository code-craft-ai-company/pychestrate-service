"""
.. module:: test_p32zzzzzzzzzzz_slo_edit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An SLO can be edited from the SLOs page (INS-12).

.. moduleauthor:: Code Craft AI LLC

The SLOs page could create and delete an objective but not change one: a typo in a name or a tighter target meant
deleting it and losing its history. Each row now has Edit (for people who may write SLOs), which opens the create form
filled in with the SLO's values, its kind shown but fixed; Save changes sends one ``PUT`` with the new values, closes the
form and shows the new numbers; a refusal (409, 422) is said in words and keeps the form open. The page is opened in a
browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
SLO_ID: str = "5a5a5a5a-0000-4000-8000-000000000001"
CONFIG: Dict[str, Any] = {"good_metric_name": "runs_ok_total", "total_metric_name": "runs_total"}


def _slo(*, name: str = "checkout", target: float = 0.99, version: int = 1) -> Dict[str, Any]:
    return {
        "slo_id": SLO_ID, "project_id": PROJECT_ID, "name": name, "description": "", "kind": "availability_ratio",
        "target": target, "window_seconds": 604800, "definition_config": CONFIG, "default_notification_route_key": None,
        "auto_attach_burn_rate_alerts": False, "version": version, "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z", "status": None,
    }


def _open(browser: Browser, *, permissions: List[str], put: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the SLOs page with one SLO. ``put`` is what an edit gets (default: 200 with the edited SLO); ``page.puts``
        collects the PUT requests' bodies and ``page.lists`` counts the list reads.
    """
    state = {"slo": _slo()}
    puts: List[Any] = []
    lists: List[int] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": permissions},
        },
    )

    def slos(route: Any) -> None:
        lists.append(1)
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": [state["slo"]], "meta": {"total": 1}}))

    def one(route: Any) -> None:
        if route.request.method != "PUT":
            route.fallback()
            return
        body = json.loads(route.request.post_data or "{}")
        puts.append(body)
        answer = put or {"status": 200, "body": None}
        if answer["status"] == 200:
            state["slo"] = _slo(name=body["name"], target=body["target"], version=2)
            payload = state["slo"]
        else:
            payload = answer["body"]
        route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(payload))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/slos(\?.*)?$"), slos)
    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/slos/[^/?]+$"), one)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/slos?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="create-toggle"]', state="attached")
    page.wait_for_timeout(1000)
    page.puts = puts
    page.lists = lists
    return page


def _row_text(page: Any) -> str:
    """The table's text (its cells render in the table's shadow root)."""
    return " ".join(page.evaluate("() => document.querySelector('mj-data-table').shadowRoot.textContent").split())


def test_edit_fills_the_form_with_the_slo_fixes_its_kind_and_saves_with_one_put(browser: Browser):
    """
    **Feature: SLO edit (INS-12)**
    **Property: Edit opens the form titled with the SLO's name, filled with its name, target, window and config, the
    kind shown but disabled; changing the target and choosing Save changes sends one PUT (the SLO's own kind, the
    new values), says it was saved, closes the form and shows the new target in the list.**
    """
    page = _open(browser, permissions=["system:slos.write"])
    try:
        page.locator('[data-role="edit-slo"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        heading = page.locator('[data-role="edit-heading"]').inner_text()
        filled = (
            page.locator('[data-role="edit-name"] input').input_value(),
            page.locator('[data-role="edit-target"] input').input_value(),
            page.locator('[data-role="edit-window"] input').input_value(),
            json.loads(page.locator('[data-role="edit-config"] textarea').input_value()),
            page.locator('[data-role="edit-kind"]').evaluate("el => el.hasAttribute('disabled')"),
            page.locator('[data-role="edit-submit"]').inner_text(),
        )
        lists_before = len(page.lists)
        page.locator('[data-role="edit-target"] input').fill("0.95")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_function("() => document.querySelector('[data-role=\"edit-form\"]') === null || document.querySelector('[data-role=\"create-region\"]').hidden === true")
        page.wait_for_timeout(600)
        toast = " ".join(page.locator('[data-role="toast-region"]').inner_text().split())
        region_hidden = page.locator('[data-role="create-region"]').evaluate("el => el.hidden")
        listed = _row_text(page)
        puts = list(page.puts)
        lists_after = len(page.lists)
    finally:
        page.context.close()

    testbase.assert_equal(
        (heading, filled, puts, "saved" in toast, region_hidden, "95.0%" in listed and "99.0%" not in listed, lists_after > lists_before),
        (
            "Edit the SLO “checkout”",
            ("checkout", "0.99", "604800", CONFIG, True, "Save changes"),
            [{"name": "checkout", "kind": "availability_ratio", "target": 0.95, "window_seconds": 604800, "definition_config": CONFIG}],
            True, True, True, True,
        ),
    )
    return


def test_a_refused_edit_says_why_and_keeps_the_form_open_for_another_try(browser: Browser):
    """
    **Feature: SLO edit (INS-12)**
    **Property: a name another SLO already has (409) is said in words and the form stays open with the person's
    values (a second attempt is possible); Cancel closes the form without sending anything.**
    """
    page = _open(browser, permissions=["system:slos.write"], put={"status": 409, "body": {"detail": "SLO name already exists in project."}})
    try:
        page.locator('[data-role="edit-slo"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        page.locator('[data-role="edit-name"] input').fill("search")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_function("() => document.querySelector('[data-role=\"toast-region\"]').textContent.trim().length > 0")
        page.wait_for_timeout(300)
        toast = " ".join(page.locator('[data-role="toast-region"]').inner_text().replace("\u00D7", "").split())
        still_open = page.locator('[data-role="edit-form"]').count() == 1 and page.locator('[data-role="create-region"]').evaluate("el => el.hidden") is False
        kept = page.locator('[data-role="edit-name"] input').input_value()
        sent = len(page.puts)
        page.locator('[data-role="edit-cancel"]').click()
        page.wait_for_timeout(200)
        closed = page.locator('[data-role="create-region"]').evaluate("el => el.hidden")
        after_cancel = len(page.puts)
    finally:
        page.context.close()

    testbase.assert_equal(
        (toast, still_open, kept, sent, closed, after_cancel),
        ("Another SLO already has that name.", True, "search", 1, True, 1),
    )
    return


def test_without_the_write_permission_there_is_no_edit_button(browser: Browser):
    """
    **Feature: SLO edit (INS-12)**
    **Property: a person who may not write SLOs is not offered Edit (it follows the same permission as Create and
    Delete).**
    """
    page = _open(browser, permissions=["system:slos.read"])
    try:
        shown = page.locator('[data-role="edit-slo"]').evaluate("el => el.hidden || getComputedStyle(el).display === 'none'")
    finally:
        page.context.close()

    testbase.assert_equal(shown, True)
    return
