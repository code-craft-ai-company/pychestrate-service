"""
.. module:: test_p31zzzk_run_results_view_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The run page says which tests failed and why (ORC-10).

.. moduleauthor:: Code Craft AI LLC

A failed run's page showed passed/failed tiles and artifact links, so finding
the failing test meant downloading a summary. The run page now has a "Test
results" section: the totals, the failing tests first with the exception and its
message (the first one already open) and a collapsible stack with the source
lines, a "failed only" toggle, and "Show more" for long runs. Test output is pod
output, so it is shown as text. The real run page is opened in a browser against
stubbed API answers.
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

RUN_ID: str = "0f6c2c1e-8888-4000-8000-000000000001"
PROJECT_ID: str = "0f6c2c1e-8888-4000-8000-000000000002"


def _run(state: str = "failed") -> Dict[str, Any]:
    return {
        "run_id": RUN_ID, "project_id": PROJECT_ID, "state": state, "terminal_outcome": "failure" if state == "failed" else None,
        "job_type": "testbase", "created_at": "2026-09-29T10:00:00+00:00", "started_at": "2026-09-29T10:00:05+00:00",
        "progress_summary": {"tests_passed": 2, "tests_failed": 1, "percent_complete": 100},
    }


def _item(name: str, result: str = "PASSED", problems: Optional[List[Dict[str, Any]]] = None, seconds: float = 0.4) -> Dict[str, Any]:
    return {
        "task_id": "t-" + name, "test_name": name, "result": result, "started_at": "2026-09-29T10:00:06+00:00",
        "finished_at": "2026-09-29T10:00:07+00:00", "duration_seconds": seconds, "problems": problems or [],
    }


FAILURE: Dict[str, Any] = {
    "kind": "failure", "type": "AssertionError", "message": "EXPECTED: 2\nFOUND: 1",
    "frames": [
        {"file": "/lab/testbase/verification.py", "line": 143, "scope": "assert_equal", "code": []},
        {"file": "/lab/ccai/tests/test_fails.py", "line": 7, "scope": "test_fails_on_purpose", "code": ["6: def test_fails_on_purpose():", "7:     testbase.assert_equal(1, 2)"]},
    ],
}


def _open(browser: Browser, *, state: str = "failed", results: Any = None, results_status: int = 200, run_extra: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the run page. ``results`` is the body of ``/results`` (or a callable of
        the query); the requests made to it are collected on ``page.results_queries``.
        ``run_extra`` adds fields to the run the API stub answers with.
    """
    queries: List[Dict[str, str]] = []

    def answer(query: Dict[str, str]) -> Any:
        queries.append(query)
        return results(query) if callable(results) else results

    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs={
            "/api/v1/runs/" + RUN_ID: dict(_run(state), **(run_extra or {})),
            "/api/v1/runs/{}/results".format(RUN_ID): answer,
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
        },
    )
    if results_status != 200:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/runs/" + RUN_ID + r"/results(\?.*)?$"),
            lambda route: route.fulfill(status=results_status, headers={"Content-Type": "application/json"}, body=b"{}"),
        )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.results_queries = queries
    page.goto(FAKE_ORIGIN + "/runs/" + RUN_ID)
    page.wait_for_selector('[data-role="progress-section"]')
    page.wait_for_timeout(1200)
    return page


def _page_of(items: List[Dict[str, Any]], by_result: Dict[str, int], total: Optional[int] = None) -> Dict[str, Any]:
    return {"items": items, "meta": {"page": 1, "per_page": 50, "total": len(items) if total is None else total, "by_result": by_result, "next_cursor": None}}


def test_a_failed_run_lists_its_failing_test_first_with_the_reason(browser: Browser):
    """
    **Feature: run results (ORC-10)**
    **Property: the section shows "1 failed · 2 passed"; the failing test is the
    first row and is open, showing "AssertionError: EXPECTED: 2 / FOUND: 1"; its
    stack lists both frames with file, line and scope and the test's source
    lines; a passing test is a plain row with nothing to open.**
    """
    body = _page_of(
        [_item("ccai.tests.test_fails#test_fails_on_purpose", "FAILED", [FAILURE], 1.25), _item("ccai.tests.test_ok#test_one"), _item("ccai.tests.test_ok#test_two", seconds=0.002)],
        {"FAILED": 1, "PASSED": 2},
    )
    page = _open(browser, results=body)
    try:
        summary = page.locator('[data-role="results-summary"]').inner_text()
        rows = page.locator('[data-role="results-list"] > li')
        first = rows.nth(0)
        first_open = first.locator("details").first.evaluate("(el) => el.open")
        message = first.locator('[data-role="problem-message"]').inner_text()
        stack_label = first.locator(".pyc-run-detail__stack summary").inner_text()
        page.locator(".pyc-run-detail__stack summary").click()
        where = first.locator(".pyc-run-detail__frame-where").all_inner_texts()
        code = first.locator(".pyc-run-detail__frame-code").inner_text()
        chips = [rows.nth(index).locator(".pyc-run-detail__result-chip").inner_text() for index in range(3)]
        durations = [rows.nth(index).locator(".pyc-run-detail__result-duration").inner_text() for index in range(3)]
        passing_details = rows.nth(1).locator("details").count()
    finally:
        page.context.close()

    testbase.assert_equal(
        (summary, first_open, message, stack_label, where, code, chips, durations, passing_details),
        (
            "1 failed · 2 passed", True, "AssertionError: EXPECTED: 2\nFOUND: 1", "Stack (2 frames)",
            ["/lab/testbase/verification.py:143 · assert_equal", "/lab/ccai/tests/test_fails.py:7 · test_fails_on_purpose"],
            "6: def test_fails_on_purpose():\n7:     testbase.assert_equal(1, 2)",
            ["failed", "passed", "passed"], ["1.25 s", "400 ms", "2 ms"], 0,
        ),
    )
    return


def test_failed_only_and_show_more_ask_the_server_for_what_they_show(browser: Browser):
    """
    **Feature: run results (ORC-10)**
    **Property: with 120 tests the first request asks for page 1 and offers
    "Show more (70 left)", which asks for page 2 and appends its rows; the toggle
    asks again for the failed tests only (``failed=true``, page 1), replaces the
    list, and offers to show all tests again.**
    """
    def answer(query: Dict[str, str]) -> Any:
        if query.get("failed") == "true":
            return _page_of([_item("t.failing", "FAILED", [FAILURE])], {"FAILED": 1, "PASSED": 119})
        start = (int(query.get("page", "1")) - 1) * 50
        items = [_item("t.test_{:03d}".format(number)) for number in range(start, min(start + 50, 120))]
        return _page_of(items, {"FAILED": 1, "PASSED": 119}, total=120)

    page = _open(browser, results=answer)
    try:
        first_rows = page.locator('[data-role="results-list"] > li').count()
        more = page.locator('[data-role="results-more"]').inner_text()
        page.locator('[data-role="results-more"]').click()
        page.wait_for_timeout(600)
        after_more = page.locator('[data-role="results-list"] > li').count()
        page.locator('[data-role="results-filter"]').click()
        page.wait_for_timeout(600)
        only_rows = page.locator('[data-role="results-list"] > li').count()
        toggle_label = page.locator('[data-role="results-filter"]').inner_text()
        queries = [(q.get("page"), q.get("failed")) for q in page.results_queries]
    finally:
        page.context.close()

    testbase.assert_equal(
        (first_rows, more, after_more, only_rows, toggle_label, queries),
        (50, "Show more (70 left)", 100, 1, "Show all tests", [("1", None), ("2", None), ("1", "true")]),
    )
    return


def test_test_output_is_shown_as_text_and_stays_inside_its_row(browser: Browser):
    """
    **Feature: run results (ORC-10)**
    **Property: a test name, exception message or source line that contains
    markup is shown as text (no element is created from it), and a very long
    unbroken name and message wrap inside the row instead of running past it.**
    """
    hostile = {
        "kind": "failure", "type": "E<b>", "message": "<img src=x onerror=window.pwned=1>" + "y" * 400,
        "frames": [{"file": "/a/b.py", "line": 1, "scope": "<i>s</i>", "code": ["<script>window.pwned=2</script>"]}],
    }
    long_name = "ccai.tests." + "very_long_module_name_" * 12 + "#test_it"
    page = _open(browser, results=_page_of([_item("<b>bold</b>" + long_name, "FAILED", [hostile])], {"FAILED": 1}))
    try:
        page.locator(".pyc-run-detail__stack summary").click()
        injected = page.locator('[data-role="results-section"] img, [data-role="results-section"] script, [data-role="results-section"] b, [data-role="results-section"] i').count()
        pwned = page.evaluate("() => window.pwned === undefined")
        text = page.locator('[data-role="problem-message"]').inner_text()
        fits = page.evaluate(
            """() => {
                const row = document.querySelector('[data-role="results-list"] > li').getBoundingClientRect();
                const inside = (el) => el.getBoundingClientRect().right <= row.right + 1;
                return [...document.querySelectorAll('.pyc-run-detail__result-name, .pyc-run-detail__problem-message, .pyc-run-detail__frame-code')].every(inside);
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (injected, pwned, text.startswith("E<b>: <img src=x onerror=window.pwned=1>"), fits),
        (0, True, True, True),
    )
    return


def test_no_recorded_tests_a_failed_request_and_a_running_run_each_say_the_right_thing(browser: Browser):
    """
    **Feature: run results (ORC-10)**
    **Property: a finished run with no per-test results says none were recorded;
    a failed results request says the results could not be loaded (and the run
    page still shows); a run that has not finished shows no results section
    and never asks for them.**
    """
    page = _open(browser, results=_page_of([], {}))
    try:
        empty = page.locator('[data-role="results-empty"]').inner_text()
    finally:
        page.context.close()

    page = _open(browser, results={}, results_status=500)
    try:
        failed = page.locator('[data-role="results-error"]').inner_text()
        run_still_shown = page.locator('[data-role="progress-section"]').count()
    finally:
        page.context.close()

    page = _open(browser, state="running", results=_page_of([], {}))
    try:
        running = (page.locator('[data-role="results-section"]').inner_text().strip(), len(page.results_queries))
    finally:
        page.context.close()

    testbase.assert_equal(
        (empty, failed, run_still_shown, running),
        ("No individual test results were recorded for this run.", "Couldn't load the test results.", 1, ("", 0)),
    )
    return


def test_the_run_page_says_who_triggered_the_run_when_it_is_known(browser: Browser):
    """
    **Feature: who triggered a run (ORC-11)**
    **Property: a run started by a user shows "Triggered by" with their name beside the other
    facts; a run with no recorded user shows no such field (nothing is invented).**
    """
    page = _open(browser, results=_page_of([], {}), run_extra={"triggered_by": "Ada Lovelace"})
    try:
        labels = page.locator(".pyc-run-detail__grid dt").all_inner_texts()
        index = labels.index("Triggered by") if "Triggered by" in labels else -1
        value = page.locator(".pyc-run-detail__grid dd").nth(index).inner_text() if index >= 0 else None
    finally:
        page.context.close()
    page = _open(browser, results=_page_of([], {}), run_extra={"triggered_by": None})
    try:
        unknown = "Triggered by" in page.locator(".pyc-run-detail__grid dt").all_inner_texts()
    finally:
        page.context.close()

    testbase.assert_equal((value, unknown), ("Ada Lovelace", False))
    return
