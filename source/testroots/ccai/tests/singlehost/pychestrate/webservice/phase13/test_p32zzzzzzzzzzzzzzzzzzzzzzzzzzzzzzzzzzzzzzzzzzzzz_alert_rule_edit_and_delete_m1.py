"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_alert_rule_edit_and_delete_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An alert rule can be edited and deleted from its page (ORC-26).

.. moduleauthor:: Code Craft AI LLC

An alert rule could be created and disabled over REST, but the page offered no way to fix a mistyped threshold or a wrong name, and no way to remove a rule
that was no longer wanted. Each row now has Edit and Delete (for those who may write alert rules). Edit opens the create form filled in with the rule's values
(its kind cannot change); Save changes sends one PUT; a refusal is said in words and keeps the form open. Delete asks first, naming the rule and how to stop
a rule without losing it, then sends one DELETE. The page is opened in a browser against stubbed API answers.
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

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000002"
RULE_ID: str = "7b7b7b7b-0000-4000-8000-000000000001"
WRITE = "system:metric_alerts.write"


def _rule(*, name: str = "failure spike", threshold: float = 5.0, metric: str = "runs_total", enabled: bool = True) -> Dict[str, Any]:
    return {
        "rule_id": RULE_ID, "project_id": PROJECT_ID, "name": name, "description": "", "kind": "threshold",
        "config": {"metric_name": metric, "op": ">=", "threshold": threshold, "window_seconds": 1800},
        "severity": "critical", "enabled": enabled, "notification_targets": ["ops-pager", "slack:#alerts"],
        "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z", "live_state": None,
    }


def _open(browser: Browser, *, permissions: List[str], rule: Optional[Dict[str, Any]] = None, put: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the Alert rules page with one rule. ``put`` is what an edit gets (default: 200 with the edited rule); ``page.puts`` and
        ``page.deletes`` collect the requests' bodies, ``page.lists`` counts the list reads.
    """
    state: Dict[str, Any] = {"rule": rule or _rule(), "gone": False}
    puts: List[Any] = []
    deletes: List[int] = []
    lists: List[int] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": permissions},
            "/api/v1/metrics/catalog": {"items": [{"name": "runs_total", "kind": "counter", "label_names": []}, {"name": "pods_ready", "kind": "gauge", "label_names": []}]},
        },
    )

    def rules(route: Any) -> None:
        if route.request.method != "GET":
            route.fallback()
            return
        lists.append(1)
        items = [] if state["gone"] else [state["rule"]]
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": items, "meta": {"total": len(items)}}))

    def one(route: Any) -> None:
        method = route.request.method
        if method == "PUT":
            body = json.loads(route.request.post_data or "{}")
            puts.append(body)
            answer = put or {"status": 200, "body": None}
            if answer["status"] == 200:
                state["rule"] = _rule(name=body["name"], threshold=body["config"]["threshold"], metric=body["config"]["metric_name"], enabled=body["enabled"])
                payload = state["rule"]
            else:
                payload = answer["body"]
            route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(payload))
        elif method == "DELETE":
            deletes.append(1)
            state["gone"] = True
            route.fulfill(status=204, body="")
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/metric-alerts(\?.*)?$"), rules)
    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/metric-alerts/[^/?]+$"), one)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/metric-alerts?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="create-toggle"]', state="attached")
    page.wait_for_timeout(1200)
    page.puts = puts
    page.deletes = deletes
    page.lists = lists
    return page


def _table_text(page: Any) -> str:
    """The table's text (its cells render in the table's shadow root)."""
    return " ".join(page.evaluate("() => { const t = document.querySelector('mj-data-table'); return t ? t.shadowRoot.textContent : ''; }").split())


def _toast(page: Any) -> str:
    return " ".join(page.locator('[data-role="toast"], [class*="__toast-message"]').first.inner_text().split())


def test_edit_fills_the_form_with_the_rule_and_saves_with_one_put(browser: Browser):
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: Edit opens the form titled with the rule's name and filled with its name, metric, comparison, threshold, window, severity,
    targets and enabled state, with "Save changes"; changing the threshold and saving sends one PUT (the rule's own kind, the new values), says it was
    saved, closes the form and shows the new threshold in the list.**
    """
    page = _open(browser, permissions=[WRITE])
    try:
        page.locator('[data-role="edit-rule"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(400)
        heading = page.locator('[data-role="edit-heading"]').inner_text()
        filled = (
            page.locator('[data-role="edit-name"] input').input_value(),
            page.locator('[data-role="edit-metric"]').evaluate("el => el.value"),
            page.locator('[data-role="edit-comparison"]').evaluate("el => el.value"),
            page.locator('[data-role="edit-threshold"] input').input_value(),
            page.locator('[data-role="edit-window"] input').input_value(),
            page.locator('[data-role="edit-severity"]').evaluate("el => el.value"),
            page.locator('[data-role="edit-targets"] input').input_value(),
            page.locator('[data-role="edit-enabled"]').is_checked(),
            page.locator('[data-role="edit-submit"]').inner_text(),
        )
        lists_before = len(page.lists)
        page.locator('[data-role="edit-threshold"] input').fill("12")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_function("() => document.querySelector('[data-role=\"create-region\"]').hidden === true")
        page.wait_for_timeout(700)
        toast = _toast(page)
        after = _table_text(page)
        puts = page.puts
        refreshed = len(page.lists) - lists_before
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            heading, filled, len(puts), puts[0]["kind"], puts[0]["config"], puts[0]["severity"], puts[0]["enabled"], puts[0]["notification_targets"],
            "saved" in toast, "12" in after, refreshed,
        ),
        (
            "Edit alert rule “failure spike”",
            ("failure spike", "runs_total", ">=", "5", "1800", "critical", "ops-pager, slack:#alerts", True, "Save changes"),
            1, "threshold", {"metric_name": "runs_total", "op": ">=", "threshold": 12, "window_seconds": 1800}, "critical", True, ["ops-pager", "slack:#alerts"],
            True, True, 1,
        ),
    )
    return


def test_a_refused_edit_is_said_in_words_and_keeps_the_form_open(browser: Browser):
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: a 409 from the API reads "Another alert rule already has that name.", the form stays open with what was typed and the list is not
    re-read; Cancel closes the form and sends nothing.**
    """
    page = _open(browser, permissions=[WRITE], put={"status": 409, "body": {"detail": "Alert rule name already exists in project."}})
    try:
        page.locator('[data-role="edit-rule"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(300)
        lists_before = len(page.lists)
        page.locator('[data-role="edit-name"] input').fill("taken name")
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_timeout(800)
        toast = _toast(page)
        still_open = page.locator('[data-role="edit-form"]').count() == 1
        typed = page.locator('[data-role="edit-name"] input').input_value()
        refreshed = len(page.lists) - lists_before
        page.locator('[data-role="edit-cancel"]').click()
        page.wait_for_timeout(300)
        closed = page.locator('[data-role="create-region"]').evaluate("el => el.hidden")
        puts = len(page.puts)
    finally:
        page.context.close()

    testbase.assert_equal(
        ("Another alert rule already has that name." in toast, still_open, typed, refreshed, closed, puts), (True, True, "taken name", 0, True, 1),
    )
    return


def test_a_rule_whose_metric_is_not_in_the_catalog_keeps_it(browser: Browser):
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: a rule on a metric the catalog no longer lists opens with that metric still offered and chosen (so its name shows, not a blank), and
    saving sends that metric back unchanged (not the first one in the catalog).**
    """
    page = _open(browser, permissions=[WRITE], rule=_rule(metric="retired_metric_total"))
    try:
        page.locator('[data-role="edit-rule"]').click()
        page.wait_for_selector('[data-role="edit-form"]')
        page.wait_for_timeout(400)
        chosen = page.locator('[data-role="edit-metric"]').evaluate("el => el.value")
        offered = page.locator('[data-role="edit-metric"] mj-option[value="retired_metric_total"]').count()
        page.locator('[data-role="edit-submit"]').click()
        page.wait_for_timeout(800)
        sent = page.puts[0]["config"]["metric_name"]
    finally:
        page.context.close()

    testbase.assert_equal((chosen, offered, sent), ("retired_metric_total", 1, "retired_metric_total"))
    return


def test_delete_asks_first_naming_the_rule_and_sends_one_delete_when_confirmed(browser: Browser):
    """
    **Feature: alert rule delete (ORC-26)**
    **Property: Delete opens a dialog naming the rule and saying it cannot be undone and how to stop a rule without losing it; Cancel sends nothing; confirming sends
    one DELETE, says the rule was deleted and the list no longer shows it.**
    """
    page = _open(browser, permissions=[WRITE])
    try:
        page.locator('[data-role="delete-rule"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        text = " ".join(page.locator("dialog.pyc-confirm").inner_text().split())
        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        after_cancel = len(page.deletes)
        page.locator('[data-role="delete-rule"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(900)
        toast = _toast(page)
        remaining = _table_text(page)
        deletes = len(page.deletes)
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            "Delete the alert rule “failure spike”?" in text, "cannot be undone" in text, "untick Enabled" in text, after_cancel,
            deletes, "deleted" in toast, "failure spike" in remaining,
        ),
        (True, True, True, 0, 1, True, False),
    )
    return


def test_without_the_write_permission_there_is_no_edit_or_delete(browser: Browser):
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: a viewer who may only read alert rules sees the rule but no Edit or Delete button; one who may write sees both.**
    """
    reader = _open(browser, permissions=["system:metric_alerts.read"])
    try:
        reader_buttons = [reader.locator('[data-role="edit-rule"]').count(), reader.locator('[data-role="delete-rule"]').count()]
        reader_visible = [reader.locator('[data-role="edit-rule"]').is_visible() if reader_buttons[0] else False, reader.locator('[data-role="delete-rule"]').is_visible() if reader_buttons[1] else False]
        reader_sees_rule = "failure spike" in _table_text(reader)
    finally:
        reader.context.close()
    writer = _open(browser, permissions=[WRITE])
    try:
        writer_visible = [writer.locator('[data-role="edit-rule"]').is_visible(), writer.locator('[data-role="delete-rule"]').is_visible()]
    finally:
        writer.context.close()

    testbase.assert_equal((reader_visible, reader_sees_rule, writer_visible), ([False, False], True, [True, True]))
    return
