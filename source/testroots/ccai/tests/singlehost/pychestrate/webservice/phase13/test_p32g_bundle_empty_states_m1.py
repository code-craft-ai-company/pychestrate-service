"""
.. module:: test_p32g_bundle_empty_states_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every bundle list says what is missing and what to do first (ORC-34).

.. moduleauthor:: Code Craft AI LLC

An earlier pass gave the runs, builds, catalog and pipelines lists an empty
state with a next step. The rest ("No pods defined in this project", "No SLOs
defined", "No enrolled clients yet", "No provisioning runs yet") still said what was
missing and stopped, and every project-scoped page answered "No projects exist
yet." with no way forward. All of them are now built by one helper
(``shared/empty-state.js``): what is missing, what to do first, and a link where
there is a page for the first step. The pages are opened in a browser against
stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Any, Dict, List, Optional, Tuple

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
ENVIRONMENT_ID: str = "0f6c2c1e-6666-4000-8000-0000000000e1"

ONE_PROJECT = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
NO_PROJECTS = {"items": [], "meta": {"total": 0}}
NO_ITEMS = {"items": [], "meta": {"page": 1, "per_page": 50, "total": 0}}

#: view, route, bundle, the list's API path under the project (or absolute), what its empty state says, and the link it offers
LISTS: List[Tuple[str, str, str, str, str, Optional[str]]] = [
    ("provisioning runs", "/provisioning-runs", "pyc-infra-bundle", "/api/v1/projects/{p}/provisioning-runs", "No provisioning runs in this project yet. Choose Trigger Provisioning above", "/environments"),
    ("environments", "/environments", "pyc-infra-bundle", "/api/v1/projects/{p}/environments", "No environments registered in this project yet. Choose Register Environment above", None),
    ("guards", "/blast-radius-guards", "pyc-infra-bundle", "/api/v1/projects/{p}/blast-radius-guards", "No blast-radius guards attached yet. Choose Attach Guard above", None),
    ("SLOs", "/slos", "pyc-metrics-bundle", "/api/v1/projects/{p}/slos", "No SLOs defined for this project yet. Choose Create SLO above", None),
    ("pods", "/pods", "pyc-pods-bundle", "/api/v1/projects/{p}/pod-definitions", "No pods in this project yet. A pod appears when a client enrolls", "/admin/enrollment-tokens"),
]

#: routes that work inside a project and say so when there is none
PROJECT_PAGES: List[Tuple[str, str, str]] = [
    ("/provisioning-runs", "pyc-infra-bundle", "provisioning runs"),
    ("/environments", "pyc-infra-bundle", "environments"),
    ("/blast-radius-guards", "pyc-infra-bundle", "guards"),
    ("/slos", "pyc-metrics-bundle", "SLOs"),
    ("/dashboards", "pyc-metrics-bundle", "dashboards"),
    ("/test-metrics", "pyc-metrics-bundle", "test metrics"),
    ("/pods", "pyc-pods-bundle", "pods"),
    ("/pipelines", "pyc-pipelines-bundle", "pipelines"),
    ("/test-catalog", "pyc-catalog-bundle", "test catalog"),
]


#: The two views whose empty state has more than one link or depends on filters
#: (a filtered runs list offers "Clear filters"; the test metrics page links to the
#: Test catalog with its own marker) and so are still built by hand. A new one must
#: use the helper, not be added here.
BUILT_BY_HAND: List[str] = [
    "pyc-metrics-bundle/test-metrics-view.js",
    "pyc-runs-bundle/runs-list-view.js",
]


def _open(browser: Browser, path: str, bundle: str, stubs: Dict[str, Any]) -> Any:
    page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs=stubs, **DESKTOP)
    page.wait_for_timeout(1200)
    return page


def _empty_state(page: Any) -> Tuple[str, Optional[str]]:
    locator = page.locator('[data-role="empty-state"]').first
    text = " ".join(locator.inner_text().split())
    link = page.locator('[data-role="empty-state-link"]')
    return text, (link.first.get_attribute("href") if link.count() > 0 else None)


def test_an_empty_list_says_what_to_do_first_and_links_where_there_is_a_page(browser: Browser):
    """
    **Feature: empty states with a next step (ORC-34)**
    **Property: for a project with nothing in it, the provisioning runs,
    environments, guards, SLOs and pods lists each say what is missing and name the
    first step (the button to choose, or the enrollment token to mint), and the
    provisioning runs and pods lists link to the page for it.**
    """
    outcomes: Dict[str, Any] = {}
    for name, route, bundle, api_path, expected, link in LISTS:
        # The pods list answers with a bare array; the guards list needs an environment to be chosen.
        stubs = {"/api/v1/projects": ONE_PROJECT, api_path.format(p=PROJECT_ID): [] if name == "pods" else NO_ITEMS}
        if name == "guards":
            stubs["/api/v1/projects/{}/environments".format(PROJECT_ID)] = {"items": [{"environment_id": ENVIRONMENT_ID, "name": "staging", "kind": "k8s_cluster"}], "meta": {"total": 1}}
        page = _open(browser, route + "?project_id=" + PROJECT_ID, bundle, stubs)
        try:
            text, href = _empty_state(page)
        finally:
            page.context.close()
        outcomes[name] = (text.startswith(expected), href)

    testbase.assert_equal(outcomes, {name: (True, link) for name, _route, _bundle, _path, _expected, link in LISTS})
    return


def test_the_clients_and_updates_lists_link_to_the_step_that_fills_them(browser: Browser):
    """
    **Feature: empty states with a next step (ORC-34)**
    **Property: an installation with no enrolled clients is told to mint an
    enrollment token, with a link to the page; one with no Pychestrate updates
    published is told to choose Publish Release.**
    """
    clients = _open(browser, "/clients", "pyc-pods-bundle", {"/api/v1/projects": ONE_PROJECT, "/api/v1/clients": []})
    try:
        clients_state = _empty_state(clients)
    finally:
        clients.context.close()
    updates = _open(browser, "/release-channels", "pyc-ops-bundle", {"/api/v1/release-channels": NO_ITEMS})
    try:
        updates_state = _empty_state(updates)
    finally:
        updates.context.close()

    testbase.assert_equal(
        (clients_state[0].startswith("No enrolled clients yet. Mint an enrollment token"), clients_state[1], updates_state[0].startswith("No Pychestrate updates published to any channel yet. Choose Publish Release above"), updates_state[1]),
        (True, "/admin/enrollment-tokens", True, None),
    )
    return


def test_every_page_that_works_inside_a_project_offers_to_create_one_when_there_is_none(browser: Browser):
    """
    **Feature: empty states with a next step (ORC-34)**
    **Property: when no project exists, each page that shows one project's data
    says "No projects exist yet", why, and links to /projects/create, and does not
    also ask the person to "select a project" (the two lines contradicted each
    other).**
    """
    outcomes: Dict[str, Any] = {}
    for route, bundle, name in PROJECT_PAGES:
        page = _open(browser, route, bundle, {"/api/v1/projects": NO_PROJECTS})
        try:
            text, href = _empty_state(page)
            asks_to_select = page.locator('[data-role="no-project-state"], [data-role="needs-project"]').count()
        finally:
            page.context.close()
        outcomes[name] = (text.startswith("No projects exist yet. This page works inside a project, so create one first."), href, asks_to_select)

    testbase.assert_equal(outcomes, {name: (True, "/projects/create", 0) for _route, _bundle, name in PROJECT_PAGES})
    return


def test_the_views_that_build_an_empty_state_use_the_shared_helper():
    """
    **Feature: empty states with a next step (ORC-34)**
    **Property: no bundle view builds an ``empty-state`` element by hand except the
    two listed in BUILT_BY_HAND: every other one gets it from
    ``shared/empty-state.js`` (so its wording and markup are the same everywhere).**
    """
    root = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir,
        "site", "ccai", "pychestrate", "webservice", "webinterface", "static", "javascript",
    )
    by_hand: List[str] = []
    for path in glob.glob(os.path.join(root, "pyc-*-bundle", "*.js")):
        if os.path.basename(path) == "index.js":
            continue
        source = open(path, encoding="utf-8").read()
        for match in re.finditer(r'setAttribute\(\s*"data-role",\s*"empty-state"\s*\)', source):
            by_hand.append(os.path.relpath(path, root))
    helper = open(os.path.join(root, "shared", "empty-state.js"), encoding="utf-8").read()

    testbase.assert_equal((sorted(set(by_hand)), 'setAttribute("data-role", "empty-state")' in helper), (sorted(BUILT_BY_HAND), True))
    return
