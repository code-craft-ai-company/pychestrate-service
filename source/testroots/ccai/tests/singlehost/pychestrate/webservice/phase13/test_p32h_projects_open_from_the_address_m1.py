"""
.. module:: test_p32h_projects_open_from_the_address_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A link to a project's page opens that project's page (ORC-27).

.. moduleauthor:: Code Craft AI LLC

Six bundle views (provisioning runs, environments, blast-radius guards, SLOs,
alert rules and test metrics) always opened on the first project. Provisioning
runs even wrote the project into the address, so a shared link with
``?project_id=<second project>`` opened the first project and then rewrote its own
address to match. Each now opens on the project the address names (when the
person may see it, otherwise the first) and keeps it in the address. The pages
are opened in a browser against stubbed API answers.
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
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

FIRST: str = "0f6c2c1e-6666-4000-8000-000000000001"
SECOND: str = "0f6c2c1e-6666-4000-8000-000000000002"

TWO_PROJECTS = {
    "items": [
        {"project_id": FIRST, "display_name": "Alpha", "slug": "alpha"},
        {"project_id": SECOND, "display_name": "Beta", "slug": "beta"},
    ],
    "meta": {"total": 2},
}

VIEWS: List[Tuple[str, str, str]] = [
    ("provisioning runs", "/provisioning-runs", "pyc-infra-bundle"),
    ("environments", "/environments", "pyc-infra-bundle"),
    ("guards", "/blast-radius-guards", "pyc-infra-bundle"),
    ("SLOs", "/slos", "pyc-metrics-bundle"),
    ("alert rules", "/metric-alerts", "pyc-metrics-bundle"),
    ("test metrics", "/test-metrics", "pyc-metrics-bundle"),
]


#: Pages that already read the project from the address and now also write it back
#: (a project the person cannot see is kept as typed there, so they are not in the
#: fall-back test), and the clients list, whose "All projects" leaves the address bare.
KEPT_VIEWS: List[Tuple[str, str, str]] = [
    ("pods", "/pods", "pyc-pods-bundle"),
    ("resource pools", "/resource-pools", "pyc-resources-bundle"),
    ("clients", "/clients", "pyc-pods-bundle"),
]


def _open(browser: Browser, path: str, bundle: str) -> Any:
    page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs={"/api/v1/projects": TWO_PROJECTS}, **DESKTOP)
    page.wait_for_timeout(1500)
    return page


def _state(page: Any) -> Tuple[str, str]:
    """``(the project the page's selector shows, the project_id in the address)``."""
    selected = page.evaluate("() => { const el = document.querySelector('[data-role=\"project-select\"]'); return el === null ? '' : String(el.value); }")
    address = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query).get("project_id", [""])[0]
    return selected, address


def test_a_page_opens_on_the_project_its_address_names_and_keeps_it(browser: Browser):
    """
    **Feature: the selected project in the address (ORC-27)**
    **Property: opening each of the six pages, and the pods, resource pools and clients
    pages, with ``?project_id=<second project>`` shows the second project in its
    selector and keeps it in the address (the first project is not chosen, and the
    address is not rewritten to it).**
    """
    outcomes: Dict[str, Any] = {}
    for name, route, bundle in VIEWS + KEPT_VIEWS:
        page = _open(browser, route + "?project_id=" + SECOND, bundle)
        try:
            outcomes[name] = _state(page)
        finally:
            page.context.close()

    testbase.assert_equal(outcomes, {name: (SECOND, SECOND) for name, _route, _bundle in VIEWS + KEPT_VIEWS})
    return


def test_without_a_project_in_the_address_the_first_is_chosen_and_written(browser: Browser):
    """
    **Feature: the selected project in the address (ORC-27)**
    **Property: opening a page with no project, or one the person cannot see, shows
    the first project and writes it into the address.**
    """
    outcomes: Dict[str, Any] = {}
    for name, route, bundle in VIEWS:
        bare = _open(browser, route, bundle)
        try:
            bare_state = _state(bare)
        finally:
            bare.context.close()
        unknown = _open(browser, route + "?project_id=00000000-0000-4000-8000-00000000dead", bundle)
        try:
            unknown_state = _state(unknown)
        finally:
            unknown.context.close()
        outcomes[name] = (bare_state, unknown_state)

    testbase.assert_equal(outcomes, {name: ((FIRST, FIRST), (FIRST, FIRST)) for name, _route, _bundle in VIEWS})
    return


def test_the_clients_list_with_all_projects_leaves_the_address_bare(browser: Browser):
    """
    **Feature: the selected project in the address (ORC-27)**
    **Property: the clients list opened with no project shows "All projects" and
    does not put a project into the address.**
    """
    page = _open(browser, "/clients", "pyc-pods-bundle")
    try:
        state = _state(page)
    finally:
        page.context.close()

    testbase.assert_equal(state, ("", ""))
    return
