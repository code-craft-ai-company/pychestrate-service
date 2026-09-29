"""
.. module:: test_p31zzs_empty_states_next_step_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An empty list says how to fill it and links to where (ORC-34).

.. moduleauthor:: Code Craft AI LLC

The bundle lists said "No runs yet", "No builds yet" and "No pipelines cached
yet" and stopped; the Builds page said "No projects exist yet." and "Select a
project to view its builds." together; the Test metrics page showed "Pass rate
0%" for a project with no runs. Each now says why it is empty, how to fill it
and, where there is a page for the first step, links to it. The pages are
opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"

ONE_PROJECT = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
NO_PROJECTS = {"items": [], "meta": {"total": 0}}
NO_ITEMS = {"items": [], "meta": {"page": 1, "per_page": 50, "total": 0}}


def _open(browser: Browser, path: str, bundle: str, stubs: Dict[str, Any]) -> Any:
    page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs=stubs, **DESKTOP)
    page.wait_for_timeout(1200)
    return page


def _text(page: Any, selector: str) -> str:
    return " ".join(page.locator(selector).first.inner_text().split())


def test_an_empty_runs_list_says_how_a_run_starts_and_links_to_each_place(browser: Browser):
    """
    **Feature: empty states name the next step (ORC-34)**
    **Property: with no runs and no filters the Runs page explains that a run
    starts from the Test catalog, a pipeline or a build, and links to each.**
    """
    page = _open(browser, "/runs", "pyc-runs-bundle", {"/api/v1/projects": ONE_PROJECT, "/api/v1/runs": NO_ITEMS})
    try:
        text = _text(page, '[data-role="empty-state"]')
        links = page.evaluate("() => [...document.querySelectorAll('.pyc-runs-list__empty-actions a')].map((a) => [a.textContent.trim(), a.getAttribute('href')])")
    finally:
        page.context.close()

    testbase.assert_equal(
        ("A run starts when you run tests from the Test catalog" in text, links),
        (True, [["Open the Test catalog", "/test-catalog"], ["Open Pipelines", "/pipelines"], ["Open Builds", "/builds"]]),
    )
    return


def test_the_builds_page_does_not_contradict_itself_when_there_are_no_projects(browser: Browser):
    """
    **Feature: empty states name the next step (ORC-34)**
    **Property: with no projects the Builds page says so once, links to
    creating one, and does not also ask the person to select a project.**
    """
    page = _open(browser, "/builds", "pyc-builds-bundle", {"/api/v1/projects": NO_PROJECTS})
    try:
        body = " ".join(page.locator("pyc-builds").first.inner_text().split()) if page.locator("pyc-builds").count() else " ".join(page.locator("main").first.inner_text().split())
        create = page.locator('[data-role="create-project"]').first.get_attribute("href")
        asks_to_select = page.locator('[data-role="no-project-state"]').count()
    finally:
        page.context.close()

    testbase.assert_equal(
        ("No projects exist yet" in body, "Select a project to view its builds" in body, create, asks_to_select),
        (True, False, "/projects/create", 0),
    )
    return


def test_a_project_with_no_builds_says_how_to_start_one(browser: Browser):
    """
    **Feature: empty states name the next step (ORC-34)**
    **Property: a project with no builds is told to use Trigger Build, not
    just "No builds yet".**
    """
    page = _open(
        browser, "/builds?project_id=" + PROJECT_ID, "pyc-builds-bundle",
        {"/api/v1/projects": ONE_PROJECT, "/api/v1/projects/{}/builds".format(PROJECT_ID): NO_ITEMS},
    )
    try:
        text = _text(page, '[data-role="empty-state"]')
    finally:
        page.context.close()

    testbase.assert_equal(text, "No builds in this project yet. Choose Trigger Build above to start one.")
    return


def test_a_project_with_no_pipelines_says_where_to_define_one_and_the_form_is_not_called_upsert(browser: Browser):
    """
    **Feature: empty states name the next step (ORC-34, ORC-37)**
    **Property: an empty Pipelines page says to paste a pipeline document into
    the form above; the form's heading is "Define a pipeline", not "Create /
    Upsert Pipeline".**
    """
    page = _open(
        browser, "/pipelines?project_id=" + PROJECT_ID, "pyc-pipelines-bundle",
        {"/api/v1/projects": ONE_PROJECT, "/api/v1/projects/{}/pipelines".format(PROJECT_ID): NO_ITEMS},
    )
    try:
        text = _text(page, '[data-role="empty-state"]')
        headings = page.evaluate("() => [...document.querySelectorAll('h1, h2, h3, h4')].map((h) => h.textContent.trim())")
    finally:
        page.context.close()

    testbase.assert_equal(
        ("Define a pipeline" in text, "cached" in text, "Define a pipeline" in headings, any("Upsert" in heading for heading in headings)),
        (True, False, True, False),
    )
    return


def test_test_metrics_with_no_runs_is_not_a_pass_rate_of_zero(browser: Browser):
    """
    **Feature: empty states name the next step (ORC-34)**
    **Property: with no test runs the Test metrics page says there is nothing
    to measure and links to the Test catalog, and shows no "Pass rate" card;
    with runs it shows the cards.**
    """
    empty = {"summary": {"run_count": 0, "pass_rate": 0, "fail_rate": 0, "failed_run_rate": 0, "tests_total": 0, "average_run_duration_seconds": 0}, "recent_runs": []}
    full = {"summary": {"run_count": 4, "pass_rate": 0.9, "fail_rate": 0.1, "failed_run_rate": 0.25, "tests_total": 40, "average_run_duration_seconds": 90}, "recent_runs": []}
    results: List[Any] = []
    for summary in (empty, full):
        page = _open(
            browser, "/test-metrics?project_id=" + PROJECT_ID, "pyc-metrics-bundle",
            {"/api/v1/projects": ONE_PROJECT, "/api/v1/projects/{}/test-metrics".format(PROJECT_ID): summary},
        )
        try:
            results.append((
                page.locator('[data-role="empty-state"]').count(),
                page.locator('[data-role="rollup-cards"]').count(),
                page.locator('[data-role="empty-next-step"]').first.get_attribute("href") if page.locator('[data-role="empty-next-step"]').count() else None,
            ))
        finally:
            page.context.close()

    testbase.assert_equal(results, [(1, 0, "/test-catalog?project_id=" + PROJECT_ID), (0, 1, None)])
    return
