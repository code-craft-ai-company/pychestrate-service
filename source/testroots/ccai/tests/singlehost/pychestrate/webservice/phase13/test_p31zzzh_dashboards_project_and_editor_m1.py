"""
.. module:: test_p31zzzh_dashboards_project_and_editor_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Dashboards keep their project, the editor is reachable, and Save follows the changes (ORC-16, ORC-33).

.. moduleauthor:: Code Craft AI LLC

The dashboard list picked a project, but the detail page and the editor always
loaded from the *first* project, so a dashboard in any other project answered
"not found"; nothing linked to the editor at all, and its Save button was always
enabled. The project now travels in the address (list, links, detail, editor),
the detail page offers "Edit layout" to a viewer who may change dashboards, Save
is enabled only when the layout differs from the last saved one, and leaving with
unsaved tiles asks first. Actions the viewer's permissions rule out are left out
(the shared ``may`` helper), and shown when the permissions cannot be read.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from typing import Any, Dict, List, Optional, Tuple

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

ALPHA: str = "0f6c2c1e-7777-4000-8000-00000000000a"
BETA: str = "0f6c2c1e-7777-4000-8000-00000000000b"
BOARD: str = "0f6c2c1e-7777-4000-8000-0000000000d1"
WRITE: List[str] = ["system:dashboards.read", "system:dashboards.write"]
READ_ONLY: List[str] = ["system:dashboards.read"]

BOARD_RECORD: Dict[str, Any] = {
    "dashboard_id": BOARD, "project_id": BETA, "name": "Ops board", "description": "", "version": 3, "tiles": [],
}


def _open(
        browser: Browser, path: str, *, permissions: Optional[List[str]] = WRITE
    ) -> Tuple[Any, List[str], List[Dict[str, Any]]]:
    """
        Open ``path`` with two projects, of which only the second holds the
        dashboard; ``permissions=None`` makes the permissions request fail.

        :returns: (page, API GET paths requested, PATCH bodies sent)
    """
    requested: List[str] = []
    patched: List[Dict[str, Any]] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [
                {"project_id": ALPHA, "display_name": "Alpha", "slug": "alpha"},
                {"project_id": BETA, "display_name": "Beta", "slug": "beta"},
            ], "meta": {"total": 2}},
            "/api/v1/projects/{}/dashboards".format(ALPHA): {"items": [], "meta": {"total": 0}},
            "/api/v1/projects/{}/dashboards".format(BETA): {"items": [BOARD_RECORD], "meta": {"total": 1}},
            "/api/v1/projects/{}/dashboards/{}".format(BETA, BOARD): BOARD_RECORD,
            "/api/v1/metrics/catalog": {"items": [{"name": "pychestrate_runs_total", "kind": "counter", "label_names": []}]},
            "/api/v1/me/permissions": {"permissions": permissions if permissions is not None else []},
        },
    )
    if permissions is None:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/me/permissions(\?.*)?$"),
            lambda route: route.fulfill(status=500, headers={"Content-Type": "application/json"}, body=b"{}"),
        )

    def dashboard(route: Any) -> None:
        request = route.request
        if request.method == "PATCH":
            patched.append(json.loads(request.post_data))
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"dashboard_id": BOARD, "version": 4}).encode("utf-8"))
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/dashboards/[^/?]+(\?.*)?$"), dashboard)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.on("request", lambda request: requested.append(request.url[len(FAKE_ORIGIN):].split("?")[0]) if "/api/v1/projects" in request.url else None)
    page.goto(FAKE_ORIGIN + path)
    return page, requested, patched


def _query(page: Any) -> str:
    return page.evaluate("() => window.location.search")


def test_the_list_opens_on_the_project_in_the_address_and_its_links_carry_it(browser: Browser):
    """
    **Feature: dashboards keep their project (ORC-16)**
    **Property: ``?project_id=`` selects that project (not the first), a link to
    a dashboard names the project, and choosing another project writes it into
    the address; a list opened without one settles on the first project and says
    so in the address.**
    """
    page, requested, _patched = _open(browser, "/dashboards?project_id={}".format(BETA))
    try:
        page.wait_for_selector('[data-role="dashboards-table"] a')
        href = page.locator('[data-role="dashboards-table"] a').first.get_attribute("href")
        listed_from = [path for path in requested if path.endswith("/dashboards")]
        page.evaluate(
            "(id) => { const s = document.querySelector('[data-role=\"project-select\"]'); s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); }",
            ALPHA,
        )
        page.wait_for_timeout(300)
        chosen = _query(page)
        page.goto(FAKE_ORIGIN + "/dashboards")
        page.wait_for_selector('[data-role="project-select"]')
        page.wait_for_timeout(800)
        defaulted = _query(page)
    finally:
        page.context.close()

    testbase.assert_equal(
        (href, listed_from, chosen, defaulted),
        (
            "/dashboards/{}?project_id={}".format(BOARD, BETA),
            ["/api/v1/projects/{}/dashboards".format(BETA)],
            "?project_id={}".format(ALPHA),
            "?project_id={}".format(ALPHA),
        ),
    )
    return


def test_the_detail_page_loads_from_the_addressed_project_and_offers_edit_layout(browser: Browser):
    """
    **Feature: dashboards keep their project (ORC-16)**
    **Property: a dashboard whose project is in the address loads from that
    project (never from the first one), shows its name, links back to that
    project's list, and offers "Edit layout" to the editor for the same
    project.**
    """
    page, requested, _patched = _open(browser, "/dashboards/{}?project_id={}".format(BOARD, BETA))
    try:
        page.wait_for_selector('[data-role="edit-layout"]')
        heading = page.locator('[data-role="dashboard-heading"]').inner_text()
        edit = page.locator('[data-role="edit-layout"]').get_attribute("href")
        back = page.locator('[data-role="back-link"]').get_attribute("href")
        fetched = [path for path in requested if "/dashboards/" in path]
    finally:
        page.context.close()

    testbase.assert_equal(
        (heading, edit, back, fetched),
        (
            "Ops board",
            "/dashboards/{}/edit?project_id={}".format(BOARD, BETA),
            "/dashboards?project_id={}".format(BETA),
            ["/api/v1/projects/{}/dashboards/{}".format(BETA, BOARD)],
        ),
    )
    return


def test_write_actions_follow_the_viewers_permissions_and_survive_an_unreadable_answer(browser: Browser):
    """
    **Feature: actions the viewer cannot use are left out (ORC-33)**
    **Property: a viewer without ``system:dashboards.write`` gets no "Edit
    layout" link and no "Create Dashboard" button; one who holds it gets both;
    when the permissions cannot be read the actions stay (the server decides).**
    """
    seen: Dict[str, Tuple[int, bool]] = {}
    for name, permissions in (("read-only", READ_ONLY), ("writer", WRITE), ("unknown", None)):
        page, _requested, _patched = _open(browser, "/dashboards/{}?project_id={}".format(BOARD, BETA), permissions=permissions)
        try:
            page.wait_for_selector('[data-role="dashboard-heading"]')
            page.wait_for_function("() => document.querySelector('[data-role=\"dashboard-heading\"]').textContent === 'Ops board'")
            page.wait_for_timeout(500)
            links = page.locator('[data-role="edit-layout"]').count()
            page.goto(FAKE_ORIGIN + "/dashboards?project_id={}".format(BETA))
            page.wait_for_selector('[data-role="create-toggle"]', state="attached")
            page.wait_for_timeout(600)
            seen[name] = (links, page.locator('[data-role="create-toggle"]').is_visible())
        finally:
            page.context.close()

    testbase.assert_equal(seen, {"read-only": (0, False), "writer": (1, True), "unknown": (1, True)})
    return


def test_save_is_offered_only_after_a_change_and_goes_to_the_dashboards_project(browser: Browser):
    """
    **Feature: the dashboard editor (ORC-16)**
    **Property: opened for a dashboard in the second project, the editor saves to
    that project; Save is disabled until a tile is added, enabled after, and
    disabled again once saved; leaving asks first only while there are unsaved
    tiles; the link to the saved dashboard and the link back keep the project.**
    """
    page, _requested, patched = _open(browser, "/dashboards/{}/edit?project_id={}".format(BOARD, BETA))

    def disabled() -> bool:
        return page.locator('[data-role="save-layout"]').get_attribute("disabled") is not None

    def would_ask() -> bool:
        return page.evaluate("() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; }")

    try:
        page.wait_for_selector('[data-role="add-tile"]')
        page.wait_for_timeout(500)
        before = (disabled(), would_ask())
        page.click('[data-role="add-tile"]')
        page.wait_for_timeout(300)
        changed = (disabled(), would_ask())
        page.click('[data-role="save-layout"]')
        page.wait_for_selector('a:has-text("Open the saved dashboard")')
        page.wait_for_timeout(300)
        after = (disabled(), would_ask())
        saved_link = page.locator('a:has-text("Open the saved dashboard")').get_attribute("href")
        back = page.locator('[data-role="dashboard-link"]').get_attribute("href")
    finally:
        page.context.close()

    testbase.assert_equal(
        (before, changed, after, len(patched), len(patched[0]["tiles"]) if patched else -1, saved_link, back),
        (
            (True, False), (False, True), (True, False), 1, 1,
            "/dashboards/{}?project_id={}".format(BOARD, BETA),
            "/dashboards/{}?project_id={}".format(BOARD, BETA),
        ),
    )
    return


def test_a_viewer_who_cannot_change_dashboards_is_told_so_instead_of_getting_a_dead_form(browser: Browser):
    """
    **Feature: actions the viewer cannot use are left out (ORC-33)**
    **Property: without ``system:dashboards.write`` the editor shows why it
    cannot be used and no tile form, so nothing is typed that cannot be saved.**
    """
    page, _requested, _patched = _open(browser, "/dashboards/{}/edit?project_id={}".format(BOARD, BETA), permissions=READ_ONLY)
    try:
        page.wait_for_selector('[data-role="read-only-notice"]')
        notice = page.locator('[data-role="read-only-notice"]').inner_text()
        forms = page.locator('[data-role="add-tile-form"]').count()
    finally:
        page.context.close()

    testbase.assert_equal(
        (notice, forms),
        ("You can view this layout but not change it. Ask an administrator for dashboard write access.", 0),
    )
    return
