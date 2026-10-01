"""
.. module:: test_p32zzzz_states_read_as_words_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A run's state reads as words, not as its stored spelling (ORC-38).

.. moduleauthor:: Code Craft AI LLC

The Runs list and the run, build and provisioning pages showed a run's state as stored:
``dispatch_unconfirmed``, ``progress_stalled``, ``needs_investigation``. A state now reads with its
underscores as spaces ("dispatch unconfirmed") on the chip and in the state filter; the stored value is still
what the colour, the filter query and the CSV export use. Opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict, List

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-9999-4000-8000-000000000001"
PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}


def _run(number: int, state: str) -> Dict[str, Any]:
    return {
        "run_id": "aaaaaaaa-0000-4000-8000-00000000000{}".format(number), "project_id": PROJECT_ID, "job_name": "nightly", "job_type": "testbase",
        "state": state, "created_at": "2026-09-29T10:00:00+00:00", "started_at": None, "completed_at": None,
    }


def test_the_runs_list_chips_and_state_filter_read_as_words_and_the_query_keeps_the_stored_value(browser: Browser):
    """
    **Feature: states as words (ORC-38)**
    **Property: the chips read "dispatch unconfirmed", "needs investigation" and "completed"; the state filter
    lists "dispatch unconfirmed" and the other underscore states with spaces; choosing one still asks the API for
    the stored value (``state=dispatch_unconfirmed``).**
    """
    runs = {"items": [_run(1, "dispatch_unconfirmed"), _run(2, "needs_investigation"), _run(3, "completed")], "meta": {"page": 1, "per_page": 50, "total": 3}}
    asked: List[str] = []
    page = open_shell_page(
        browser, path="/runs?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/runs": runs}, **DESKTOP,
    )
    page.context.on("request", lambda request: asked.append(urllib.parse.urlparse(request.url).query) if urllib.parse.urlparse(request.url).path == "/api/v1/runs" else None)
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(800)
        chips = [text.strip() for text in page.locator("mj-data-table mj-chip").all_inner_texts()]
        options = [text.strip() for text in page.locator('[data-role="state-filter"] mj-option').all_inner_texts()]
        page.locator('[data-role="state-filter"]').click()
        page.get_by_role("option", name="dispatch unconfirmed").click()
        page.wait_for_timeout(600)
        filtered = any("state=dispatch_unconfirmed" in query for query in asked)
    finally:
        page.context.close()

    testbase.assert_equal(
        (sorted(chips), [option for option in options if "_" in option], "dispatch unconfirmed" in options, "needs investigation" in options, filtered),
        (["completed", "dispatch unconfirmed", "needs investigation"], [], True, True, True),
    )
    return
