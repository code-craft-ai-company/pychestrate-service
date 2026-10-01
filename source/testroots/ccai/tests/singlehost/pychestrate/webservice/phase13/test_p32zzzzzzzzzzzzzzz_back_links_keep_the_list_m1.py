"""
.. module:: test_p32zzzzzzzzzzzzzzz_back_links_keep_the_list_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: "Back to ..." on the pod, client, environment and resource pages returns to the list as it was (ORC-27).

.. moduleauthor:: Code Craft AI LLC

The runs, builds, provisioning, pipeline and dashboard pages already sent "Back to ..." to the list as the person left
it. The pod, client, environment, pool and resource pages still went to a bare list (the client and environment pages
dropped the project, so a person working in the second project came back to the first). Their back links now go back in
history when the page was opened from that list, and otherwise point at the list of the page's own project. The pages
are opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict

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

FIRST: str = "0f6c2c1e-1111-4000-8000-00000000000a"
SECOND: str = "0f6c2c1e-1111-4000-8000-00000000000b"
CLIENT: str = "0f6c2c1e-1111-4000-8000-0000000000c1"
POD: str = "0f6c2c1e-1111-4000-8000-0000000000d1"
ENVIRONMENT: str = "0f6c2c1e-1111-4000-8000-0000000000e1"

PROJECTS = {"items": [
    {"project_id": FIRST, "display_name": "First", "slug": "first"},
    {"project_id": SECOND, "display_name": "Second", "slug": "second"},
], "meta": {"total": 2}}

CLIENT_RECORD = {
    "client_id": CLIENT, "pod_name": "lab-pod", "status": "ACTIVE", "liveness_state": "ALIVE", "project_id": SECOND,
    "created_at": "2026-09-29T10:00:00+00:00", "last_seen": "2026-09-29T10:05:00+00:00", "capabilities": [],
}
POD_RECORD = {
    "pod_id": POD, "project_id": SECOND, "pod_name": "lab-pod", "description": "", "created_at": "2026-09-29T10:00:00+00:00",
}
ENVIRONMENT_RECORD = {
    "environment_id": ENVIRONMENT, "project_id": SECOND, "name": "lab", "kind": "lab", "state": "ready", "description": "",
    "created_at": "2026-09-29T10:00:00+00:00",
}

STUBS: Dict[str, Any] = {
    "/api/v1/projects": PROJECTS,
    "/api/v1/clients": [CLIENT_RECORD],
    "/api/v1/clients/" + CLIENT: CLIENT_RECORD,
    "/api/v1/projects/{}/pod-definitions".format(SECOND): [POD_RECORD],
    "/api/v1/projects/{}/pod-definitions/{}".format(SECOND, POD): POD_RECORD,
    "/api/v1/projects/{}/environments".format(SECOND): {"items": [ENVIRONMENT_RECORD], "meta": {"total": 1}},
    "/api/v1/projects/{}/environments/{}".format(SECOND, ENVIRONMENT): ENVIRONMENT_RECORD,
}


def _context(browser: Browser, bundle: str) -> Any:
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs=STUBS)
    return context


def _query(url: str) -> Dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


def _from_the_list_and_back(context: Any, *, list_url: str, link: str, detail_path: str) -> Dict[str, str]:
    """Open the list in the second project, follow the row link, follow Back; return the list address's query."""
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + list_url)
    page.wait_for_selector(link)
    page.wait_for_timeout(500)
    page.locator(link).first.click()
    page.wait_for_selector('[data-role="back-link"]')
    page.wait_for_timeout(800)
    opened = urllib.parse.urlparse(page.url).path
    page.locator('[data-role="back-link"]').click()
    page.wait_for_timeout(1200)
    returned = urllib.parse.urlparse(page.url)
    query = _query(page.url)
    return {"opened": opened == detail_path, "path": returned.path, "project_id": query.get("project_id", ""), "marker": query.get("marker", "")}


def test_back_from_a_client_returns_to_the_clients_of_the_project_it_was_opened_from(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: from the clients list in the second project (with another parameter the list does not know), opening a client and following "Back to
    clients" lands on the clients list with its whole address as it was (the link went back in history); a client page opened on its own points its back link at the list of
    the client's own project (it used to point at the bare list, which opens on the first project).**
    """
    context = _context(browser, "pyc-pods-bundle")
    try:
        went = _from_the_list_and_back(
            context, list_url="/clients?project_id=" + SECOND + "&marker=kept", link="a.pyc-clients-list__client-link", detail_path="/clients/" + CLIENT,
        )
        direct = context.new_page()
        direct.set_default_timeout(READY_TIMEOUT_MS)
        direct.goto(FAKE_ORIGIN + "/clients/" + CLIENT)
        direct.wait_for_selector('[data-role="back-link"]')
        direct.wait_for_timeout(1000)
        href = direct.locator('[data-role="back-link"]').get_attribute("href")
    finally:
        context.close()

    testbase.assert_equal((went, href), ({"opened": True, "path": "/clients", "project_id": SECOND, "marker": "kept"}, "/clients?project_id=" + SECOND))
    return


def test_back_from_a_pod_returns_to_the_pods_of_the_project_it_was_opened_from(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: from the pods list in the second project, opening a pod and following "Back to pods" lands on the pods
    list still in the second project.**
    """
    context = _context(browser, "pyc-pods-bundle")
    try:
        went = _from_the_list_and_back(
            context, list_url="/pods?project_id=" + SECOND + "&marker=kept", link="a.pyc-pods-list__pod-link", detail_path="/pods/" + POD,
        )
    finally:
        context.close()

    testbase.assert_equal(went, {"opened": True, "path": "/pods", "project_id": SECOND, "marker": "kept"})
    return


def test_back_from_an_environment_returns_to_the_environments_of_its_project(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: from the environments list in the second project, opening an environment and following "All
    environments" lands on the list still in the second project; an environment page opened on its own (it carries
    its project in the address) points the link at that project's list.**
    """
    context = _context(browser, "pyc-infra-bundle")
    try:
        went = _from_the_list_and_back(
            context, list_url="/environments?project_id=" + SECOND + "&marker=kept", link='[data-role="environment-link"]', detail_path="/environments/" + ENVIRONMENT,
        )
        direct = context.new_page()
        direct.set_default_timeout(READY_TIMEOUT_MS)
        direct.goto(FAKE_ORIGIN + "/environments/{}?project_id={}".format(ENVIRONMENT, SECOND))
        direct.wait_for_selector('[data-role="back-link"]')
        href = direct.locator('[data-role="back-link"]').get_attribute("href")
    finally:
        context.close()

    testbase.assert_equal((went, href), ({"opened": True, "path": "/environments", "project_id": SECOND, "marker": "kept"}, "/environments?project_id=" + SECOND))
    return
