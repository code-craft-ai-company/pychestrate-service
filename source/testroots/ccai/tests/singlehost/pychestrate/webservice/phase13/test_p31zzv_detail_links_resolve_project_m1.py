"""
.. module:: test_p31zzv_detail_links_resolve_project_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A build or provisioning run opens from its id alone (E2E-38).

.. moduleauthor:: Code Craft AI LLC

``/builds/{id}`` said "This link is missing its project context" unless the
address carried ``?project_id=``, so a link shared anywhere but the list did
not open. A build's id is also its run's id, and ``GET /api/v1/runs/{id}``
names the project: the build and provisioning run pages ask for it when the
address does not carry it, and put it in the address so a refresh keeps it. An
id that no run answers to gets a plain message. The pages are opened in a
browser against stubbed API answers and the requests they make are recorded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re
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
BUILD_ID: str = "aaaaaaaa-1111-4000-8000-000000000001"
PROVISIONING_ID: str = "bbbbbbbb-2222-4000-8000-000000000002"

BUILD = {
    "run_id": BUILD_ID, "project_id": PROJECT_ID, "runner_kind": "makefile", "repro_digest_sha256": "abcdef0123456789",
    "state": "completed", "started_at": "2026-09-29T10:00:00+00:00", "finished_at": "2026-09-29T10:01:00+00:00",
    "inputs": {}, "annotations": {}, "toolchain": [], "source": None,
}

PROVISIONING = {
    "run_id": PROVISIONING_ID, "project_id": PROJECT_ID, "environment_id": "cccccccc-3333-4000-8000-000000000003",
    "driver_name": "terraform", "action": "apply", "state": "completed",
    "started_at": "2026-09-29T10:00:00+00:00", "finished_at": "2026-09-29T10:02:00+00:00", "inputs": {},
}


def _open(browser: Browser, *, path: str, bundle: str, known: Dict[str, Any], detail_path: str, detail: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """Open a detail page; ``known`` maps a run id to its body for ``/api/v1/runs/{id}`` (others answer 404)."""
    requested: List[str] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", bundle],
        api_stubs={"/api/v1/projects": {"items": [], "meta": {"total": 0}}, detail_path: detail},
    )

    def runs_lookup(route: Any) -> None:
        run_id = urllib.parse.urlparse(route.request.url).path.rsplit("/", 1)[-1]
        if run_id in known:
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps(known[run_id]).encode("utf-8"))
        else:
            route.fulfill(status=404, headers={"Content-Type": "application/problem+json"}, body=json.dumps({"status": 404, "detail": "Run not found."}).encode("utf-8"))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/runs/[^/?]+$"), runs_lookup)
    context.on("request", lambda request: requested.append(urllib.parse.urlparse(request.url).path))
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    page.wait_for_selector('[data-role="back-link"]')
    page.wait_for_timeout(1500)
    return page, requested


def test_a_build_link_without_a_project_resolves_the_project_from_the_run(browser: Browser):
    """
    **Feature: links that open (E2E-38)**
    **Property: ``/builds/{id}`` with no query asks ``/api/v1/runs/{id}`` for
    the project, loads the build from the project's endpoint, shows it, and
    puts ``project_id`` in the address.**
    """
    page, requested = _open(
        browser, path="/builds/" + BUILD_ID, bundle="pyc-builds-bundle", known={BUILD_ID: {"run_id": BUILD_ID, "project_id": PROJECT_ID}},
        detail_path="/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID), detail=BUILD,
    )
    try:
        errors = page.locator('[data-role="error-state"]').count()
        text = " ".join(page.locator("pyc-build-detail").inner_text().split())
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))
    finally:
        page.context.close()

    testbase.assert_equal(
        (errors, "makefile" in text, query.get("project_id"), "/api/v1/runs/" + BUILD_ID in requested, "/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID) in requested),
        (0, True, PROJECT_ID, True, True),
    )
    return


def test_a_build_link_that_carries_its_project_does_not_ask_again(browser: Browser):
    """
    **Feature: links that open (E2E-38)**
    **Property: with ``?project_id=`` in the address the run is not looked up.**
    """
    page, requested = _open(
        browser, path="/builds/{}?project_id={}".format(BUILD_ID, PROJECT_ID), bundle="pyc-builds-bundle", known={},
        detail_path="/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID), detail=BUILD,
    )
    try:
        errors = page.locator('[data-role="error-state"]').count()
    finally:
        page.context.close()

    testbase.assert_equal((errors, "/api/v1/runs/" + BUILD_ID in requested), (0, False))
    return


def test_an_id_no_run_answers_to_gets_a_plain_message(browser: Browser):
    """
    **Feature: links that open (E2E-38)**
    **Property: when the run lookup answers 404 the page says no build with
    this id could be found (not "missing its project context") and never
    requests a build.**
    """
    page, requested = _open(
        browser, path="/builds/" + BUILD_ID, bundle="pyc-builds-bundle", known={},
        detail_path="/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID), detail=BUILD,
    )
    try:
        text = " ".join(page.locator('[data-role="error-state"]').first.inner_text().split())
    finally:
        page.context.close()

    testbase.assert_equal(
        (text.startswith("No build with this id could be found"), "missing its project" in text, any("/builds/" in path and path.startswith("/api/v1/projects/") for path in requested)),
        (True, False, False),
    )
    return


def test_a_provisioning_run_link_without_a_project_opens_too(browser: Browser):
    """
    **Feature: links that open (E2E-38)**
    **Property: ``/provisioning-runs/{id}`` with no query resolves the project
    the same way and shows the run's action and driver.**
    """
    page, requested = _open(
        browser, path="/provisioning-runs/" + PROVISIONING_ID, bundle="pyc-infra-bundle",
        known={PROVISIONING_ID: {"run_id": PROVISIONING_ID, "project_id": PROJECT_ID}},
        detail_path="/api/v1/projects/{}/provisioning-runs/{}".format(PROJECT_ID, PROVISIONING_ID), detail=PROVISIONING,
    )
    try:
        errors = page.locator('[data-role="error-state"]').count()
        text = " ".join(page.locator("pyc-provisioning-detail").inner_text().split())
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))
    finally:
        page.context.close()

    testbase.assert_equal(
        (errors, "terraform" in text, query.get("project_id")),
        (0, True, PROJECT_ID),
    )
    return
