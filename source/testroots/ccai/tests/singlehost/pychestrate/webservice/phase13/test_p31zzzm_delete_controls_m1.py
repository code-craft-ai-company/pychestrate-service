"""
.. module:: test_p31zzzm_delete_controls_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SLOs and pipelines can be deleted, after a confirmation that says what is lost (ORC-26, XC-15).

.. moduleauthor:: Code Craft AI LLC

The SLO list and the pipeline page had no way to delete what the API lets a
person delete. Each now has a Delete action that asks first, in the shell's own
dialog (Cancel focused, the deed named on its button), through the new
``pyc-confirm-request`` event the shell answers; a refusal, a missing record and
an unreachable server each get their own message. The real pages are opened in a
browser against stubbed API answers, and the DELETE requests are captured.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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
    open_fixture_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-aaaa-4000-8000-000000000001"
SLO_ID: str = "0f6c2c1e-aaaa-4000-8000-0000000000a1"
PIPELINE_ID: str = "b" * 64

SLO = {
    "slo_id": SLO_ID, "project_id": PROJECT_ID, "name": "API availability", "kind": "availability_ratio",
    "target": 0.999, "window_seconds": 86400, "definition_config": {},
}
PIPELINE = {
    "pipeline_id": PIPELINE_ID, "project_id": PROJECT_ID, "name": "release", "schema_version": 1, "stages": [],
    "filename": "pipeline.yaml", "commit_sha": "abcdef1234", "cached_at": "2026-09-29T10:00:00+00:00",
}


def _open(browser: Browser, *, path: str, bundle: str, stubs: Dict[str, Any], delete_status: int = 204) -> Any:
    """
        Open ``path``; a DELETE to the record answers ``delete_status`` and is collected
        on ``page.deletes`` (together with the SLO list requests on ``page.lists``).
    """
    deletes: List[str] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", bundle],
        api_stubs=dict({
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": ["system:slos.write", "system:pipelines.write"]},
        }, **stubs),
    )

    def delete(route: Any) -> None:
        request = route.request
        if request.method == "DELETE":
            deletes.append(request.url[len(FAKE_ORIGIN):])
            if delete_status == 0:
                route.abort()
            else:
                route.fulfill(status=delete_status, headers={"Content-Type": "application/json"}, body=b"" if delete_status == 204 else b"{}")
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/(slos|pipelines)/[^/?]+(\?.*)?$"), delete)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.deletes = deletes
    page.goto(FAKE_ORIGIN + path)
    return page


def _dialog(page: Any) -> Tuple[str, str, Optional[str], str]:
    """(message, accept label, focused button's role, dialog title) of the shell's confirm dialog."""
    page.wait_for_selector("dialog.pyc-confirm[open]")
    return (
        page.locator("dialog.pyc-confirm .pyc-confirm__message").inner_text(),
        page.locator('[data-role="confirm-accept"]').inner_text(),
        page.evaluate("() => document.activeElement && document.activeElement.getAttribute('data-role')"),
        page.locator("dialog.pyc-confirm .pyc-confirm__title").inner_text(),
    )


def _slo_page(browser: Browser, *, delete_status: int = 204) -> Any:
    listed = {"items": [SLO], "meta": {"total": 1}}
    page = _open(
        browser, path="/slos?project_id=" + PROJECT_ID, bundle="pyc-metrics-bundle", delete_status=delete_status,
        stubs={"/api/v1/projects/{}/slos".format(PROJECT_ID): listed},
    )
    page.wait_for_selector('[data-role="delete-slo"]')
    page.wait_for_timeout(500)
    return page


def test_deleting_an_slo_asks_first_in_the_shells_dialog_and_cancel_does_nothing(browser: Browser):
    """
    **Feature: delete controls (ORC-26, XC-15)**
    **Property: the SLO's Delete opens the shell's modal dialog naming the SLO and
    what goes with it, with "Cancel" focused and "Delete SLO" on the acting
    button; Cancel (and Escape) send no request and leave the row.**
    """
    page = _slo_page(browser)
    try:
        page.locator('[data-role="delete-slo"]').click()
        message, accept, focused, title = _dialog(page)
        page.locator('[data-role="confirm-cancel"]').click()
        page.wait_for_timeout(300)
        page.locator('[data-role="delete-slo"]').click()
        _dialog(page)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        rows = page.locator('[data-role="slos-table"]').count()
        sent = list(page.deletes)
        open_dialogs = page.locator("dialog.pyc-confirm[open]").count()
    finally:
        page.context.close()

    testbase.assert_equal(
        (message, accept, focused, title, sent, open_dialogs, rows),
        (
            "Delete the SLO “API availability”?\n\nIts target and its burn-rate state are removed. This cannot be undone.",
            "Delete SLO", "confirm-cancel", "Please confirm", [], 0, 1,
        ),
    )
    return


def test_confirming_deletes_the_slo_and_reloads_the_list(browser: Browser):
    """
    **Feature: delete controls (ORC-26)**
    **Property: confirming sends ``DELETE /api/v1/projects/<p>/slos/<id>``, shows
    "SLO “API availability” deleted." and asks for the list again.**
    """
    page = _slo_page(browser)
    try:
        page.locator('[data-role="delete-slo"]').click()
        _dialog(page)
        page.locator('[data-role="confirm-accept"]').click()
        page.wait_for_selector('[data-role="toast"]')
        toast = page.locator('[data-role="toast"]').first.inner_text()
        sent = list(page.deletes)
    finally:
        page.context.close()

    testbase.assert_equal(
        (sent, "SLO “API availability” deleted." in toast),
        (["/api/v1/projects/{}/slos/{}".format(PROJECT_ID, SLO_ID)], True),
    )
    return


def test_a_refused_missing_or_unreachable_delete_says_which(browser: Browser):
    """
    **Feature: delete controls (ORC-26)**
    **Property: a 403 says the person may not delete SLOs, a 404 says the SLO no
    longer exists, a network failure says the service could not be reached; none
    says "deleted".**
    """
    said: Dict[int, str] = {}
    for status in (403, 404, 0):
        page = _slo_page(browser, delete_status=status)
        try:
            page.locator('[data-role="delete-slo"]').click()
            _dialog(page)
            page.locator('[data-role="confirm-accept"]').click()
            page.wait_for_selector('[data-role="toast"]')
            said[status] = page.locator('[data-role="toast"]').first.inner_text()
        finally:
            page.context.close()

    testbase.assert_equal(
        (
            "You do not have permission to delete SLOs." in said[403],
            "That SLO no longer exists." in said[404],
            "Failed to reach the SLO service." in said[0],
            any("deleted" in text for text in said.values()),
        ),
        (True, True, True, False),
    )
    return


def _pipeline_page(browser: Browser, *, delete_status: int = 204) -> Any:
    page = _open(
        browser, path="/pipelines/{}?project_id={}".format(PIPELINE_ID, PROJECT_ID), bundle="pyc-pipelines-bundle", delete_status=delete_status,
        stubs={"/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID): PIPELINE},
    )
    page.wait_for_selector('[data-role="delete-pipeline"]')
    page.wait_for_timeout(300)
    return page


def test_deleting_a_pipeline_asks_first_then_says_it_is_gone_and_links_back(browser: Browser):
    """
    **Feature: delete controls (ORC-26)**
    **Property: the pipeline page's Delete asks in the shell's dialog (naming the
    pipeline; "Delete pipeline" on the button); Cancel sends nothing; confirming
    sends the DELETE and replaces the page with "Pipeline “release” deleted." and
    a link back to that project's pipelines.**
    """
    page = _pipeline_page(browser)
    try:
        page.locator('[data-role="delete-pipeline"]').click()
        message, accept, focused, _title = _dialog(page)
        page.locator('[data-role="confirm-cancel"]').click()
        page.wait_for_timeout(300)
        sent_after_cancel = list(page.deletes)
        page.locator('[data-role="delete-pipeline"]').click()
        _dialog(page)
        page.locator('[data-role="confirm-accept"]').click()
        page.wait_for_selector('[data-role="deleted-state"]')
        state = page.locator('[data-role="deleted-state"]').inner_text()
        href = page.locator('[data-role="deleted-state"] a').get_attribute("href")
        sent = list(page.deletes)
        button_left = page.locator('[data-role="delete-pipeline"]').count()
    finally:
        page.context.close()

    testbase.assert_equal(
        (message, accept, focused, sent_after_cancel, sent, state, href, button_left),
        (
            "Delete the pipeline “release”?\n\nThe saved definition is removed from this project. This cannot be undone.",
            "Delete pipeline", "confirm-cancel", [], ["/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID)],
            "Pipeline “release” deleted. Back to pipelines", "/pipelines?project_id=" + PROJECT_ID, 0,
        ),
    )
    return


def test_a_refused_pipeline_delete_keeps_the_page_and_a_missing_one_says_so(browser: Browser):
    """
    **Feature: delete controls (ORC-26)**
    **Property: a 403 keeps the pipeline page with "You do not have permission to
    delete pipelines." and the Delete button enabled again; a 404 replaces the
    page with "This pipeline no longer exists." and the link back.**
    """
    page = _pipeline_page(browser, delete_status=403)
    try:
        page.locator('[data-role="delete-pipeline"]').click()
        _dialog(page)
        page.locator('[data-role="confirm-accept"]').click()
        page.wait_for_selector('[data-role="delete-notice"]')
        refused = (
            page.locator('[data-role="delete-notice"]').inner_text(),
            page.locator('[data-role="deleted-state"]').count(),
            page.locator('[data-role="delete-pipeline"]').get_attribute("disabled"),
        )
    finally:
        page.context.close()
    page = _pipeline_page(browser, delete_status=404)
    try:
        page.locator('[data-role="delete-pipeline"]').click()
        _dialog(page)
        page.locator('[data-role="confirm-accept"]').click()
        page.wait_for_selector('[data-role="deleted-state"]')
        missing = page.locator('[data-role="deleted-state"]').inner_text()
    finally:
        page.context.close()

    testbase.assert_equal(
        (refused, missing),
        (("You do not have permission to delete pipelines.", 0, None), "This pipeline no longer exists. Back to pipelines"),
    )
    return


def test_the_confirm_helper_uses_the_browsers_box_only_when_nothing_answers(browser: Browser):
    """
    **Feature: delete controls (XC-15)**
    **Property: with no listener for ``pyc-confirm-request`` the helper falls back to
    the browser's confirm box (accepting resolves true, dismissing false); with a
    listener that answers, no browser box appears and its answer is the result.**
    """
    page = open_fixture_page(browser, body_html="<p>fixture</p>", **DESKTOP)
    native: List[str] = []

    def on_dialog(dialog: Any) -> None:
        native.append(dialog.message)
        (dialog.accept() if len(native) == 1 else dialog.dismiss())

    page.on("dialog", on_dialog)
    try:
        ask = "async (label) => (await import('/static/javascript/shared/confirm.js')).confirm_action(document.body, 'Really?', label)"
        accepted = page.evaluate(ask, "Go")
        dismissed = page.evaluate(ask, "Go")
        boxes_before_listener = len(native)
        page.evaluate(
            "() => document.addEventListener('pyc-confirm-request', (event) => { event.preventDefault(); event.detail.resolve(event.detail.confirm_label === 'Yes please'); })"
        )
        answered = (page.evaluate(ask, "Yes please"), page.evaluate(ask, "No"))
        boxes_after_listener = len(native)
    finally:
        page.context.close()

    testbase.assert_equal(
        (accepted, dismissed, native[:2], boxes_before_listener, answered, boxes_after_listener),
        (True, False, ["Really?", "Really?"], 2, (True, False), 2),
    )
    return


def test_the_slo_row_actions_sit_apart_and_the_table_does_not_scroll_sideways(browser: Browser):
    """
    **Feature: delete controls (ORC-26)**
    **Property: at a desktop width the three row actions (Refresh Status, Edit, Delete) sit on one line with a gap
    between each, and the whole SLO table fits without a horizontal scrollbar, so no column
    (the name first) is cut off.**
    """
    page = _slo_page(browser)
    try:
        status = page.locator('[data-role="load-status"]').bounding_box()
        edit = page.locator('[data-role="edit-slo"]').bounding_box()
        delete = page.locator('[data-role="delete-slo"]').bounding_box()
        table = page.locator('[data-role="slos-table"]').bounding_box()
        overflowing = page.locator('[data-role="slos-table"]').evaluate(
            """(host) => [host, ...(host.shadowRoot ? host.shadowRoot.querySelectorAll('*') : [])].filter((el) => el.scrollWidth > el.clientWidth + 1).length"""
        )
        boxes = {
            "gap": edit["x"] - (status["x"] + status["width"]), "gap_to_delete": delete["x"] - (edit["x"] + edit["width"]),
            "one_line": abs(status["y"] - edit["y"]) < 2 and abs(edit["y"] - delete["y"]) < 2,
            "delete_right": delete["x"] + delete["width"], "table_right": table["x"] + table["width"], "overflowing": overflowing,
        }
    finally:
        page.context.close()

    testbase.assert_equal(
        (boxes["gap"] >= 4, boxes["gap_to_delete"] >= 4, boxes["one_line"], boxes["delete_right"] <= boxes["table_right"], boxes["overflowing"]),
        (True, True, True, True, 0),
    )
    return
