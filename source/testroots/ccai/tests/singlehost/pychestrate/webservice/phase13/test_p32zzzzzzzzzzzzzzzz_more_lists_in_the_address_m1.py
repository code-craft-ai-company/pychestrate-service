"""
.. module:: test_p32zzzzzzzzzzzzzzzz_more_lists_in_the_address_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The environments, clients, pods, resource pools and test catalog lists keep their filters and page in the address (ORC-27).

.. moduleauthor:: Code Craft AI LLC

The runs, builds, provisioning and pipelines lists read their filters and page from the address and write them back;
these five mirrored only the project, so a filtered or paged list could not be shared and a reload started again from the
first page. They now do the same: the environments' state, the clients' status and liveness, the test catalog's
"Include retired", and the page of each. The pages are opened in a browser against stubbed API answers; the requests they
make and the address they end with are recorded.
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
#: A page answer that says there are three pages of twenty-five, so page two is a real page.
PAGED = {"page": 2, "per_page": 25, "total": 60}


def _open(browser: Browser, *, path: str, bundle: str, api_path: str, answer: Any) -> Tuple[Any, List[Dict[str, str]]]:
    """Open a list page; return (page, the query of each request it made to ``api_path``)."""
    seen: List[Dict[str, str]] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs={"/api/v1/projects": PROJECTS, api_path: answer})

    def note(request: Any) -> None:
        parsed = urllib.parse.urlparse(request.url)
        if parsed.path == api_path:
            seen.append(dict(urllib.parse.parse_qsl(parsed.query)))

    context.on("request", note)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    page.wait_for_timeout(2500)
    return page, seen


def _query(page: Any) -> Dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def test_the_environments_list_reads_its_state_and_page_from_the_address_and_writes_them_back(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``/environments?state=frozen&page=2`` asks the API for state=frozen, page 2, shows "frozen" in the
    state filter and keeps both in its address; choosing another state writes it and drops the page.**
    """
    path = "/api/v1/projects/{}/environments".format(PROJECT_ID)
    page, seen = _open(
        browser, path="/environments?project_id={}&state=frozen&page=2".format(PROJECT_ID), bundle="pyc-infra-bundle",
        api_path=path, answer={"items": [], "meta": PAGED},
    )
    try:
        asked = (seen[-1].get("state"), seen[-1].get("page"))
        shown = page.locator('[data-role="state-filter"]').evaluate("el => el.value")
        kept = (_query(page).get("state"), _query(page).get("page"))
        page.locator('[data-role="state-filter"]').click()
        page.get_by_role("option", name="active", exact=True).click()
        page.wait_for_timeout(800)
        changed = (_query(page).get("state"), _query(page).get("page"))
    finally:
        page.context.close()

    testbase.assert_equal((asked, shown, kept, changed), (("frozen", "2"), "frozen", ("frozen", "2"), ("active", None)))
    return


def test_the_clients_list_keeps_its_status_liveness_and_page_in_the_address(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``/clients?status=REVOKED&liveness=LOST&page=2`` asks the API for exactly those filters (the list
    pages client-side), shows them in the filters and keeps them and page 2 in its address.**
    """
    page, seen = _open(
        browser, path="/clients?project_id={}&status=REVOKED&liveness=LOST&page=2".format(PROJECT_ID), bundle="pyc-pods-bundle",
        api_path="/api/v1/clients", answer={"items": [], "meta": PAGED},
    )
    try:
        asked = (seen[-1].get("status"), seen[-1].get("liveness_state"))
        shown = (page.locator('[data-role="status-filter"]').evaluate("el => el.value"), page.locator('[data-role="liveness-filter"]').evaluate("el => el.value"))
        kept = (_query(page).get("status"), _query(page).get("liveness"), _query(page).get("page"))
        page.locator('[data-role="pager"]').evaluate("el => el.dispatchEvent(new CustomEvent('mj-pagination-change', {detail: {page: 3}}))")
        page.wait_for_timeout(600)
        moved = (_query(page).get("page"), _query(page).get("status"))
    finally:
        page.context.close()

    testbase.assert_equal((asked, shown, kept, moved), (("REVOKED", "LOST"), ("REVOKED", "LOST"), ("REVOKED", "LOST", "2"), ("3", "REVOKED")))
    return


def test_a_value_the_list_does_not_know_is_ignored_not_trusted(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``?status=bogus&page=-3`` (not a client status, not a page) asks the API for no status filter and
    the address does not repeat either of them.**
    """
    page, seen = _open(
        browser, path="/clients?project_id={}&status=bogus&page=-3".format(PROJECT_ID), bundle="pyc-pods-bundle",
        api_path="/api/v1/clients", answer={"items": [], "meta": {"page": 1, "per_page": 25, "total": 0}},
    )
    try:
        asked = seen[-1].get("status")
        kept = (_query(page).get("status"), _query(page).get("page"))
    finally:
        page.context.close()

    testbase.assert_equal((asked, kept), (None, (None, None)))
    return


def test_the_test_catalog_keeps_include_retired_and_the_page_in_the_address(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``/test-catalog?include_retired=true&page=2`` asks the API for retired entries too, page 2, shows the
    box ticked and keeps both in its address; unticking it drops both from the address.**
    """
    path = "/api/v1/projects/{}/test-catalog".format(PROJECT_ID)
    page, seen = _open(
        browser, path="/test-catalog?project_id={}&include_retired=true&page=2".format(PROJECT_ID), bundle="pyc-catalog-bundle",
        api_path=path, answer={"items": [], "meta": PAGED},
    )
    try:
        asked = (seen[-1].get("include_retired"), seen[-1].get("page"))
        ticked = page.locator('[data-role="include-retired"]').is_checked()
        kept = (_query(page).get("include_retired"), _query(page).get("page"))
        page.locator('[data-role="include-retired"]').click()
        page.wait_for_timeout(800)
        cleared = (_query(page).get("include_retired"), _query(page).get("page"))
    finally:
        page.context.close()

    testbase.assert_equal((asked, ticked, kept, cleared), (("true", "2"), True, ("true", "2"), (None, None)))
    return


def test_the_pods_and_resource_pools_lists_keep_their_page_in_the_address(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``?page=2`` on the pods list and on the resource pools list is still in the address after the list
    has loaded, and choosing page 3 writes page 3 (a reload used to start again from page one).**
    """
    pods = [{"pod_id": "0f6c2c1e-1111-4000-8000-{:012d}".format(number), "project_id": PROJECT_ID, "pod_name": "pod-{}".format(number), "created_at": "2026-09-29T10:00:00+00:00"} for number in range(60)]
    pods_page, _seen = _open(
        browser, path="/pods?project_id={}&page=2".format(PROJECT_ID), bundle="pyc-pods-bundle",
        api_path="/api/v1/projects/{}/pod-definitions".format(PROJECT_ID), answer=pods,
    )
    try:
        pods_kept = _query(pods_page).get("page")
        pods_page.locator('[data-role="pager"]').evaluate("el => el.dispatchEvent(new CustomEvent('mj-pagination-change', {detail: {page: 3}}))")
        pods_page.wait_for_timeout(800)
        pods_moved = _query(pods_page).get("page")
    finally:
        pods_page.context.close()
    pools = [{"pool_id": "0f6c2c1e-2222-4000-8000-{:012d}".format(number), "project_id": PROJECT_ID, "name": "pool-{}".format(number), "created_at": "2026-09-29T10:00:00+00:00"} for number in range(60)]
    pools_page, _seen = _open(
        browser, path="/resource-pools?project_id={}&page=2".format(PROJECT_ID), bundle="pyc-resources-bundle",
        api_path="/api/v1/resource-pools", answer=pools,
    )
    try:
        pools_kept = _query(pools_page).get("page")
        pools_page.locator('[data-role="pager"]').evaluate("el => el.dispatchEvent(new CustomEvent('mj-pagination-change', {detail: {page: 3}}))")
        pools_page.wait_for_timeout(800)
        pools_moved = _query(pools_page).get("page")
    finally:
        pools_page.context.close()

    testbase.assert_equal((pods_kept, pods_moved, pools_kept, pools_moved), ("2", "3", "2", "3"))
    return
