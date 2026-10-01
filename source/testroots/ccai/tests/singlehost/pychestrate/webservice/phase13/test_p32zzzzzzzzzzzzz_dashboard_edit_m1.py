"""
.. module:: test_p32zzzzzzzzzzzzz_dashboard_edit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A dashboard can be renamed and re-described from the dashboards list (ORC-26).

.. moduleauthor:: Code Craft AI LLC

``PATCH .../dashboards/{id}`` could rename a dashboard, but the only edit the UI offered was the tile layout: a
mistyped name stayed. Each row of the dashboards list now has **Edit** (for people who may write dashboards): the
create form filled in with the name and description; Save changes sends only what changed together with the
version the list showed, so an edit never overwrites someone else's change; a name another dashboard has and a
dashboard changed meanwhile are told apart in words. The page is opened in a browser against stubbed API answers.
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

PROJECT_ID: str = "0f6c2c1e-7777-4000-8000-00000000000b"
BOARD: str = "0f6c2c1e-7777-4000-8000-0000000000d1"


def _board(*, name: str = "Ops bord", description: str = "", version: int = 3) -> Dict[str, Any]:
    return {"dashboard_id": BOARD, "project_id": PROJECT_ID, "name": name, "description": description, "version": version, "tiles": []}


def _open(browser: Browser, *, permissions: List[str], patch: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the dashboards list with one dashboard. ``patch`` is what an edit gets (default: 200 with the edited
        dashboard); ``page.patches`` collects the PATCH bodies.
    """
    current = {"board": _board()}
    patches: List[Any] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Beta", "slug": "beta"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": permissions},
        },
    )

    def collection(route: Any) -> None:
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": [current["board"]], "meta": {"total": 1}}))

    def one(route: Any) -> None:
        if route.request.method != "PATCH":
            route.fallback()
            return
        body = json.loads(route.request.post_data or "{}")
        patches.append(body)
        answer = patch or {"status": 200}
        if answer["status"] == 200:
            for key in ("name", "description"):
                if key in body:
                    current["board"][key] = body[key]
            current["board"]["version"] += 1
            payload = current["board"]
        else:
            payload = answer["body"]
        route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(payload))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/dashboards(\?.*)?$"), collection)
    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/dashboards/[^/?]+(\?.*)?$"), one)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/dashboards?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="create-toggle"]', state="attached")
    page.wait_for_timeout(1200)
    page.patches = patches
    return page


def _table_text(page: Any) -> str:
    """The table's text (its cells render in the table's shadow root)."""
    return " ".join(page.evaluate("() => document.querySelector('mj-data-table').shadowRoot.textContent").split())


def test_edit_fills_the_form_sends_only_what_changed_with_the_version_and_shows_the_new_name(browser: Browser):
    """
    **Feature: dashboard edit (ORC-26)**
    **Property: Edit opens the form titled with the dashboard's name and filled with its name and description;
    fixing the name sends one PATCH holding the new name and the version the list showed (not the unchanged
    description); the page says it was saved, closes the form and lists the new name (no description, 0 tiles) at the next version, 4.**
    """
    page = _open(browser, permissions=["system:dashboards.read", "system:dashboards.write"])
    try:
        page.locator('[data-role="edit-dashboard"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        heading = page.locator('[data-role="edit-heading"]').inner_text()
        filled = (page.locator('[data-role="edit-name-input"] input').input_value(), page.locator('[data-role="edit-description-input"] input').input_value())
        page.locator('[data-role="edit-name-input"] input').fill("Ops board")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_function("() => document.querySelector('[data-role=\"edit-form\"]') === null")
        page.wait_for_timeout(800)
        notice = " ".join(page.locator('[data-role="notice-region"]').inner_text().split())
        listed = _table_text(page)
        patches = list(page.patches)
    finally:
        page.context.close()

    testbase.assert_equal(
        (heading, filled, patches, notice, "Ops bord" in listed, "Ops board—04Edit" in listed),
        ("Edit the dashboard “Ops bord”", ("Ops bord", ""), [{"expected_version": 3, "name": "Ops board"}], "Dashboard “Ops board” saved.", False, True),
    )
    return


def test_a_description_can_be_added_and_an_unchanged_save_sends_nothing(browser: Browser):
    """
    **Feature: dashboard edit (ORC-26)**
    **Property: adding a description sends it (and not the unchanged name); saving the form as it opened says
    "Nothing to change." and sends no request; Cancel closes the form.**
    """
    page = _open(browser, permissions=["system:dashboards.read", "system:dashboards.write"])
    try:
        page.locator('[data-role="edit-dashboard"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_timeout(500)
        unchanged = (" ".join(page.locator('[data-role="notice-region"]').inner_text().split()), len(page.patches), page.locator('[data-role="edit-form"]').count())

        page.locator('[data-role="edit-dashboard"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        page.locator('[data-role="edit-description-input"] input').fill("Everything on call")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_timeout(800)
        added = list(page.patches)

        page.locator('[data-role="edit-dashboard"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.locator('[data-role="edit-cancel"]').click()
        page.wait_for_timeout(200)
        cancelled = (page.locator('[data-role="edit-form"]').count(), len(page.patches))
    finally:
        page.context.close()

    testbase.assert_equal(
        (unchanged, added, cancelled),
        (("Nothing to change.", 0, 0), [{"expected_version": 3, "description": "Everything on call"}], (0, 1)),
    )
    return


def test_a_name_clash_and_a_dashboard_changed_meanwhile_are_told_apart(browser: Browser):
    """
    **Feature: dashboard edit (ORC-26)**
    **Property: a 409 whose text is a version mismatch says someone else changed the dashboard and to refresh; a
    409 for a name another dashboard has says so; the form stays open in both cases.**
    """
    clash = _open(browser, permissions=["system:dashboards.read", "system:dashboards.write"], patch={"status": 409, "body": {"detail": "Dashboard name already exists in project.\nPROJECT_ID: x\nNAME: Ops"}})
    try:
        clash.locator('[data-role="edit-dashboard"]').click()
        clash.wait_for_selector('[data-role="edit-form"]')
        clash.wait_for_timeout(300)
        clash.locator('[data-role="edit-name-input"] input').fill("Ops")
        clash.locator('[data-role="edit-submit"]').click()
        clash.wait_for_timeout(700)
        clash_message = " ".join(clash.locator('[data-role="notice-region"]').inner_text().split())
        clash_open = clash.locator('[data-role="edit-form"]').count()
    finally:
        clash.context.close()
    stale = _open(browser, permissions=["system:dashboards.read", "system:dashboards.write"], patch={"status": 409, "body": {"detail": "Dashboard version mismatch.\nEXPECTED: 3\nACTUAL: 4"}})
    try:
        stale.locator('[data-role="edit-dashboard"]').click()
        stale.wait_for_selector('[data-role="edit-form"]')
        stale.wait_for_timeout(300)
        stale.locator('[data-role="edit-name-input"] input').fill("Ops board")
        stale.locator('[data-role="edit-submit"]').click()
        stale.wait_for_timeout(700)
        stale_message = " ".join(stale.locator('[data-role="notice-region"]').inner_text().split())
        stale_open = stale.locator('[data-role="edit-form"]').count()
    finally:
        stale.context.close()

    testbase.assert_equal(
        (clash_message, clash_open, stale_message, stale_open),
        (
            "Another dashboard in this project already has that name.", 1,
            "Someone else changed this dashboard since the list was loaded. Refresh and edit it again.", 1,
        ),
    )
    return


def test_without_the_write_permission_there_is_no_edit_button(browser: Browser):
    """
    **Feature: dashboard edit (ORC-26)**
    **Property: a person who may only read dashboards is not offered Edit (same permission as Create).**
    """
    page = _open(browser, permissions=["system:dashboards.read"])
    try:
        page.wait_for_timeout(500)
        shown = page.locator('[data-role="edit-dashboard"]').evaluate("el => !el.hidden && getComputedStyle(el).display !== 'none'")
    finally:
        page.context.close()

    testbase.assert_equal(shown, False)
    return
