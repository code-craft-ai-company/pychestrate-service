"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_dashboard_delete_buttons_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A dashboard can be deleted from its list (ORC-26).

.. moduleauthor:: Code Craft AI LLC

The dashboards list let a person create, rename and re-tile a dashboard but never remove one. Each row now has a Delete button for those who may write
dashboards: it asks first, naming the dashboard, saying how many tiles go with it and that it cannot be undone; Cancel sends nothing; confirming sends one
DELETE, says it was deleted and the list no longer shows it. The page is opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from typing import Any, Dict, List

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

PROJECT_ID: str = "0f6c2c1e-7777-4000-8000-00000000000c"
BOARD: str = "0f6c2c1e-7777-4000-8000-0000000000e1"
WRITE = "system:dashboards.write"


def _board() -> Dict[str, Any]:
    tile = {"tile_id": "t1", "kind": "metric-line-chart", "x": 0, "y": 0, "w": 6, "h": 3, "config": {"metric_name": "m1"}}
    return {"dashboard_id": BOARD, "project_id": PROJECT_ID, "name": "Ops board", "description": "", "version": 2, "tiles": [tile, dict(tile, tile_id="t2")]}


def _open(browser: Browser, *, permissions: List[str], delete_status: int = 204) -> Any:
    """Open the dashboards list with one dashboard; ``page.deletes`` counts the DELETE requests."""
    state: Dict[str, Any] = {"gone": False}
    deletes: List[int] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Beta", "slug": "beta"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": permissions},
        },
    )

    def collection(route: Any) -> None:
        items = [] if state["gone"] else [_board()]
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": items, "meta": {"total": len(items)}}))

    def one(route: Any) -> None:
        if route.request.method != "DELETE":
            route.fallback()
            return
        deletes.append(1)
        if delete_status in (204, 404):
            state["gone"] = True
        route.fulfill(status=delete_status, headers={"Content-Type": "application/json"}, body="" if delete_status == 204 else json.dumps({"detail": "Dashboard not found."}))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/dashboards(\?.*)?$"), collection)
    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/dashboards/[^/?]+(\?.*)?$"), one)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/dashboards?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="create-toggle"]', state="attached")
    page.wait_for_timeout(1200)
    page.deletes = deletes
    return page


def _table_text(page: Any) -> str:
    """The table's text (its cells render in the table's shadow root)."""
    return " ".join(page.evaluate("() => { const t = document.querySelector('mj-data-table'); return t ? t.shadowRoot.textContent : ''; }").split())


def test_delete_asks_first_naming_the_dashboard_and_its_tiles_and_sends_one_delete_when_confirmed(browser: Browser):
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: Delete opens a dialog naming the dashboard, saying its 2 tiles go with it and that it cannot be undone; Cancel sends nothing and the dashboard
    stays; confirming sends one DELETE, the page says it was deleted and the list no longer shows it.**
    """
    page = _open(browser, permissions=[WRITE])
    try:
        page.locator('[data-role="delete-dashboard"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        text = " ".join(page.locator("dialog.pyc-confirm").inner_text().split())
        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        after_cancel = (len(page.deletes), "Ops board" in _table_text(page))
        page.locator('[data-role="delete-dashboard"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(900)
        notice = " ".join(page.locator('[data-role="notice-region"]').inner_text().split())
        after = _table_text(page)
        deletes = len(page.deletes)
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            "Delete the dashboard “Ops board”?" in text, "Its 2 tiles go with it." in text, "cannot be undone" in text, after_cancel,
            deletes, "deleted" in notice, "Ops board" in after,
        ),
        (True, True, True, (0, True), 1, True, False),
    )
    return


def test_a_dashboard_that_is_already_gone_says_so_and_the_list_catches_up(browser: Browser):
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: if someone else deleted the dashboard first (404), the page says it no longer exists and the list is re-read without it.**
    """
    page = _open(browser, permissions=[WRITE], delete_status=404)
    try:
        page.locator('[data-role="delete-dashboard"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(900)
        notice = " ".join(page.locator('[data-role="notice-region"]').inner_text().split())
        after = _table_text(page)
    finally:
        page.context.close()

    testbase.assert_equal(("no longer exists" in notice, "Ops board" in after), (True, False))
    return


def test_a_refused_delete_is_said_in_words_and_the_dashboard_stays(browser: Browser):
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: a 403 reads "You do not have permission to delete dashboards." and the dashboard is still listed.**
    """
    page = _open(browser, permissions=[WRITE], delete_status=403)
    try:
        page.locator('[data-role="delete-dashboard"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(900)
        notice = " ".join(page.locator('[data-role="notice-region"]').inner_text().split())
        after = _table_text(page)
    finally:
        page.context.close()

    testbase.assert_equal(("You do not have permission to delete dashboards." in notice, "Ops board" in after), (True, True))
    return


def test_without_the_write_permission_there_is_no_delete_button(browser: Browser):
    """
    **Feature: dashboard delete (ORC-26)**
    **Property: a viewer who may only read dashboards sees the dashboard but no Delete (or Edit) button; one who may write sees both.**
    """
    reader = _open(browser, permissions=["system:dashboards.read"])
    try:
        reader_visible = [reader.locator('[data-role="edit-dashboard"]').is_visible(), reader.locator('[data-role="delete-dashboard"]').is_visible()]
        reader_sees = "Ops board" in _table_text(reader)
    finally:
        reader.context.close()
    writer = _open(browser, permissions=[WRITE])
    try:
        writer_visible = [writer.locator('[data-role="edit-dashboard"]').is_visible(), writer.locator('[data-role="delete-dashboard"]').is_visible()]
    finally:
        writer.context.close()

    testbase.assert_equal((reader_visible, reader_sees, writer_visible), ([False, False], True, [True, True]))
    return
