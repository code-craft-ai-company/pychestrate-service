"""
.. module:: test_p32zzzzzzzz_run_a_saved_pipeline_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A saved pipeline can be run from its page (ORC-13).

.. moduleauthor:: Code Craft AI LLC

A pipeline could be defined and validated in the UI but not run: the trigger API wanted the whole document
sent again, which the page does not have. The pipeline page now has a Run button (shown to people who may run
pipelines). It asks first, saying what will start and from which commit; Cancel sends nothing; Run requests the run
by the pipeline's id, the page says it started (or why it did not, with the server's reason) and refreshes the
Runs section. Opened in a browser against stubbed API answers.
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

PROJECT_ID: str = "0f6c2c1e-aaaa-4000-8000-000000000001"
PIPELINE_ID: str = "e" * 64
DIALOG = "dialog.pyc-confirm"

PIPELINE = {
    "pipeline_id": PIPELINE_ID, "project_id": PROJECT_ID, "name": "release", "schema_version": 1, "commit_sha": "1a2b3c4d5e6f",
    "filename": "ci.yaml", "cached_at": "2026-09-29T10:00:00+00:00",
    "stages": [
        {"stage_id": "build", "needs": [], "when_clause": "succeeded", "steps": []},
        {"stage_id": "test", "needs": ["build"], "when_clause": "succeeded", "steps": []},
    ],
}


def _open(browser: Browser, *, permissions: List[str], answer: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the pipeline page. ``answer`` is what the run request gets: ``{"status": ..., "body": ...}``
        (default: 201 with a run). The page's ``posts`` list collects the run requests' bodies and ``run_lists``
        counts the list reads.
    """
    answer = answer or {"status": 201, "body": {"run_id": "r1", "pipeline_id": PIPELINE_ID, "state": "running"}}
    posts: List[Any] = []
    lists: List[int] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-pipelines-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID): PIPELINE,
            "/api/v1/me/permissions": {"permissions": permissions},
        },
    )

    def runs(route: Any) -> None:
        if route.request.method == "POST":
            posts.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(answer["body"]))
        else:
            lists.append(1)
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps({"items": [], "meta": {"total": 0}}))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/pipeline-runs(\?.*)?$"), runs)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/pipelines/{}?project_id={}".format(PIPELINE_ID, PROJECT_ID))
    page.wait_for_selector('[data-role="pipeline-name"]')
    page.wait_for_timeout(800)
    page.posts = posts
    page.run_lists = lists
    return page


def test_run_asks_first_then_requests_the_run_by_the_pipelines_id_and_says_it_started(browser: Browser):
    """
    **Feature: run a saved pipeline (ORC-13)**
    **Property: Run opens a dialog naming the pipeline, its two stages and the commit; Cancel sends no
    request; confirming sends one request whose body is just the pipeline id; the page then says the run started
    and re-reads the Runs section.**
    """
    page = _open(browser, permissions=["system:pipelines.run", "system:pipelines.write"])
    try:
        page.locator('[data-role="run-pipeline"]').click()
        page.wait_for_selector(DIALOG + "[open]")
        message = " ".join(page.locator(".pyc-confirm__message").inner_text().split())
        accept = page.locator("[data-role=confirm-accept]").inner_text()
        accept_classes = page.locator("[data-role=confirm-accept]").get_attribute("class") or ""
        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        after_cancel = len(page.posts)
        lists_before = len(page.run_lists)

        page.locator('[data-role="run-pipeline"]').click()
        page.wait_for_selector(DIALOG + "[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_selector('[data-role="run-notice"]')
        page.wait_for_timeout(500)
        notice = (page.locator('[data-role="run-notice"]').inner_text(), page.locator('[data-role="run-notice"]').get_attribute("data-tone"))
        posts = list(page.posts)
        refreshed = len(page.run_lists) > lists_before
    finally:
        page.context.close()

    testbase.assert_equal(
        (message, accept, "pyc-confirm__button--primary" in accept_classes, "pyc-confirm__button--danger" in accept_classes, after_cancel, posts, notice, refreshed),
        (
            "Run the pipeline “release” now? It starts its 2 stages on this project’s pods, from commit 1a2b3c4, in the order they depend on each other.",
            "Run pipeline", True, False, 0, [{"pipeline_id": PIPELINE_ID}], ("Run started. It is listed under Runs below.", "ok"), True,
        ),
    )
    return


def test_a_refused_run_shows_the_servers_reason_and_a_person_without_the_permission_has_no_button(browser: Browser):
    """
    **Feature: run a saved pipeline (ORC-13)**
    **Property: when the service refuses (409 "No enrolled pod ...") the notice reads "The pipeline was not
    run: <reason>" in the error tone and nothing claims the run started; a viewer without the run permission is
    not shown the button.**
    """
    refusal = {"status": 409, "body": {"type": "about:blank", "title": "Conflict", "status": 409, "detail": "No enrolled pod matches the build job's requirements."}}
    page = _open(browser, permissions=["system:pipelines.run"], answer=refusal)
    try:
        page.locator('[data-role="run-pipeline"]').click()
        page.wait_for_selector(DIALOG + "[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_selector('[data-role="run-notice"]')
        refused = (page.locator('[data-role="run-notice"]').inner_text(), page.locator('[data-role="run-notice"]').get_attribute("data-tone"))
    finally:
        page.context.close()
    viewer = _open(browser, permissions=["system:pipelines.read"])
    try:
        visible = viewer.locator('[data-role="run-pipeline"]').count() > 0 and viewer.locator('[data-role="run-pipeline"]').first.is_visible()
    finally:
        viewer.context.close()

    testbase.assert_equal(
        (refused, visible),
        (("The pipeline was not run: No enrolled pod matches the build job's requirements.", "error"), False),
    )
    return
