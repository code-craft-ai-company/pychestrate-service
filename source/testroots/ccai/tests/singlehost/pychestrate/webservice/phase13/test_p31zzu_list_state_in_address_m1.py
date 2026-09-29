"""
.. module:: test_p31zzu_list_state_in_address_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A list's filters and page live in the address (ORC-27).

.. moduleauthor:: Code Craft AI LLC

``?state=failed`` was ignored, "Back to ..." returned to the bare list, and a
filtered view could not be shared. The Runs, Builds, Provisioning and
Pipelines lists now read their filters and page from the address when they
load and write them back (replacing the history entry, so Back still leaves
the page) whenever they refresh. The pages are opened in a browser against
stubbed API answers; the requests they make and the address they end with are
recorded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict, List, Tuple

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

PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
NO_ITEMS = {"items": [], "meta": {"page": 1, "per_page": 25, "total": 0}}


def _open(browser: Browser, *, path: str, bundle: str, api_path: str) -> Tuple[Any, List[Dict[str, str]]]:
    """Open a list page; return (page, the query of each list request it made)."""
    seen: List[Dict[str, str]] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", bundle],
        api_stubs={"/api/v1/projects": PROJECTS, api_path: NO_ITEMS},
    )

    def note(request: Any) -> None:
        parsed = urllib.parse.urlparse(request.url)
        if parsed.path == api_path:
            seen.append(dict(urllib.parse.parse_qsl(parsed.query)))

    context.on("request", note)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    page.wait_for_selector("mj-select")
    page.wait_for_timeout(1500)
    return page, seen


def _query(page: Any) -> Dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def _choose_state(page: Any, label: str) -> None:
    page.locator('[data-role="state-filter"]').click()
    page.get_by_role("option", name=label, exact=True).click()
    page.wait_for_timeout(700)


def test_the_runs_list_reads_its_filters_from_the_address_and_writes_them_back(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``/runs?state=failed`` asks the API for failed runs and shows
    "failed" in the State control; choosing "completed" puts ``state=completed``
    in the address and "All states" removes it, without adding history
    entries; an unknown state in the address is ignored.**
    """
    page, seen = _open(browser, path="/runs?project_id={}&state=failed".format(PROJECT_ID), bundle="pyc-runs-bundle", api_path="/api/v1/runs")
    try:
        first = seen[0]
        shown = page.evaluate("() => document.querySelector('[data-role=\"state-filter\"]').value")
        history_before = page.evaluate("() => history.length")
        _choose_state(page, "completed")
        completed = _query(page)
        requested = seen[-1]
        _choose_state(page, "All states")
        cleared = _query(page)
        history_after = page.evaluate("() => history.length")
    finally:
        page.context.close()
    bogus, bogus_seen = _open(browser, path="/runs?state=bogus", bundle="pyc-runs-bundle", api_path="/api/v1/runs")
    try:
        bogus_first = bogus_seen[0]
    finally:
        bogus.context.close()

    testbase.assert_equal(
        (first.get("state"), shown, completed.get("state"), requested.get("state"), "state" in cleared, cleared.get("project_id"), history_after - history_before, "state" in bogus_first),
        ("failed", "failed", "completed", "completed", False, PROJECT_ID, 0, False),
    )
    return


def test_the_builds_and_provisioning_lists_do_the_same(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: the Builds and Provisioning lists read ``state`` from the
    address, request it, show it, and write the chosen state and the project
    back.**
    """
    outcomes = []
    for path, bundle, api_path, chosen in (
        ("/builds?project_id={}&state=running".format(PROJECT_ID), "pyc-builds-bundle", "/api/v1/projects/{}/builds".format(PROJECT_ID), "failed"),
        ("/provisioning-runs?project_id={}&state=running".format(PROJECT_ID), "pyc-infra-bundle", "/api/v1/projects/{}/provisioning-runs".format(PROJECT_ID), "failed"),
    ):
        page, seen = _open(browser, path=path, bundle=bundle, api_path=api_path)
        try:
            first = seen[0].get("state")
            shown = page.evaluate("() => document.querySelector('[data-role=\"state-filter\"]').value")
            _choose_state(page, chosen)
            after = _query(page)
        finally:
            page.context.close()
        outcomes.append((first, shown, after.get("state"), after.get("project_id")))

    testbase.assert_equal(
        outcomes,
        [("running", "running", "failed", PROJECT_ID), ("running", "running", "failed", PROJECT_ID)],
    )
    return


def test_the_pipelines_list_keeps_its_page_and_project_in_the_address(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``/pipelines?page=2`` requests page 2 and keeps ``page=2`` and
    the project in the address; page 1 leaves no ``page`` parameter.**
    """
    page, seen = _open(browser, path="/pipelines?project_id={}&page=2".format(PROJECT_ID), bundle="pyc-pipelines-bundle", api_path="/api/v1/projects/{}/pipelines".format(PROJECT_ID))
    try:
        requested = seen[0].get("page")
        kept = _query(page)
    finally:
        page.context.close()
    plain, _seen = _open(browser, path="/pipelines?project_id=" + PROJECT_ID, bundle="pyc-pipelines-bundle", api_path="/api/v1/projects/{}/pipelines".format(PROJECT_ID))
    try:
        first_page = _query(plain)
    finally:
        plain.context.close()

    testbase.assert_equal(
        (requested, kept.get("page"), kept.get("project_id"), "page" in first_page),
        ("2", "2", PROJECT_ID, False),
    )
    return


RUN_ID: str = "aaaaaaaa-1111-4000-8000-000000000001"

ONE_RUN = {
    "items": [{
        "run_id": RUN_ID, "project_id": PROJECT_ID, "job_name": "nightly", "job_type": "testbase", "state": "failed",
        "created_at": "2026-09-29T10:00:00+00:00", "started_at": "2026-09-29T10:00:05+00:00", "completed_at": "2026-09-29T10:03:17+00:00",
    }],
    "meta": {"page": 1, "per_page": 25, "total": 1},
}


def test_back_to_the_list_from_a_detail_page_restores_the_filters(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: from ``/runs?state=failed`` a person opens a run and follows
    "Back to runs": the list comes back with ``state=failed`` in its address
    (the link went back in history); the same link on a page opened without
    coming from the list (no referrer) goes to the bare ``/runs``.**
    """
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/runs": ONE_RUN, "/api/v1/runs/" + RUN_ID: ONE_RUN["items"][0]},
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    try:
        page.goto(FAKE_ORIGIN + "/runs?project_id={}&state=failed".format(PROJECT_ID))
        page.wait_for_selector("a.pyc-runs-list__run-link")
        page.locator("a.pyc-runs-list__run-link").first.click()
        page.wait_for_selector('[data-role="back-link"]')
        opened = urllib.parse.urlparse(page.url).path
        page.locator('[data-role="back-link"]').click()
        page.wait_for_selector("mj-select")
        page.wait_for_timeout(800)
        returned = _query(page)
        direct = context.new_page()
        direct.set_default_timeout(READY_TIMEOUT_MS)
        direct.goto(FAKE_ORIGIN + "/runs/" + RUN_ID)
        direct.wait_for_selector('[data-role="back-link"]')
        direct.locator('[data-role="back-link"]').click()
        direct.wait_for_selector("mj-select")
        bare = urllib.parse.urlparse(direct.url)
    finally:
        context.close()

    testbase.assert_equal(
        (opened, returned.get("state"), returned.get("project_id"), bare.path, bare.query),
        ("/runs/" + RUN_ID, "failed", PROJECT_ID, "/runs", ""),
    )
    return


def test_the_runs_csv_link_follows_the_filters(browser: Browser):
    """
    **Feature: CSV export (ORG-F22)**
    **Property: the Runs page has a "Download CSV" link whose address is
    ``/api/v1/runs?format=csv`` plus the project and state currently chosen; it
    follows a change of state.**
    """
    page, _seen = _open(browser, path="/runs?project_id=" + PROJECT_ID, bundle="pyc-runs-bundle", api_path="/api/v1/runs")
    try:
        before = page.locator('[data-role="export-csv"]').get_attribute("href")
        _choose_state(page, "completed")
        after = page.locator('[data-role="export-csv"]').get_attribute("href")
    finally:
        page.context.close()

    def query_of(href: str) -> Dict[str, str]:
        return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(href).query))

    testbase.assert_equal(
        (urllib.parse.urlparse(before).path, query_of(before), query_of(after)),
        ("/api/v1/runs", {"format": "csv", "project_id": PROJECT_ID}, {"format": "csv", "project_id": PROJECT_ID, "state": "completed"}),
    )
    return

