"""
.. module:: test_p32u_tabs_in_the_address_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The tab a page is on is in its address (ORC-27).

.. moduleauthor:: Code Craft AI LLC

Webhooks (Inbound / Outbound) and Secrets (Org / Project / User) always opened on their
first tab: a link to the outbound subscriptions, or a reload after choosing them, went back to
Inbound. The tab is now in the address (``?tab=outbound``, ``?scope=project``), read when the page
opens and written (without adding history) when it changes; the first tab is the default and leaves
the address bare. An unknown value opens the first tab. Opened in a browser against stubbed API
answers.
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

PROJECT_ID: str = "0f6c2c1e-7777-4000-8000-000000000001"
PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
EMPTY = {"items": [], "meta": {"total": 0}}


def _webhooks(browser: Browser, query: str) -> Any:
    page = open_shell_page(
        browser, path="/webhooks?project_id=" + PROJECT_ID + query, bundle_names=["pyc-site-shell", "pyc-ops-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP,
    )
    page.wait_for_selector('[data-role="tab-inbound"]')
    page.wait_for_timeout(600)
    return page


def _secrets(browser: Browser, query: str) -> Any:
    page = open_shell_page(
        browser, path="/secrets" + query, bundle_names=["pyc-site-shell", "pyc-secrets-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/secrets": EMPTY, "/api/v1/identity/users": EMPTY}, **DESKTOP,
    )
    page.wait_for_selector('[data-role="scope-tab"]')
    page.wait_for_timeout(800)
    return page


def _selected(page: Any) -> List[str]:
    return page.evaluate("() => [...document.querySelectorAll('[role=\"tab\"]')].filter((t) => t.getAttribute('aria-selected') === 'true').map((t) => t.textContent.trim())")


def _query(page: Any) -> str:
    return page.evaluate("() => new URLSearchParams(window.location.search).get('tab') || new URLSearchParams(window.location.search).get('scope') || ''")


def test_webhooks_opens_on_the_tab_the_address_names_and_writes_changes_back(browser: Browser):
    """
    **Feature: tab in the address (ORC-27)**
    **Property: ``?tab=outbound`` opens Outbound; a bare address, and an unknown tab, open Inbound;
    choosing Outbound puts ``tab=outbound`` in the address and choosing Inbound removes it, keeping
    ``project_id``.**
    """
    named = _webhooks(browser, "&tab=outbound")
    try:
        opened = (_selected(named), _query(named))
        named.locator('[data-role="tab-inbound"]').click()
        named.wait_for_timeout(300)
        back = (_selected(named), _query(named), "project_id=" + PROJECT_ID in named.url)
        named.locator('[data-role="tab-outbound"]').click()
        named.wait_for_timeout(300)
        again = (_selected(named), _query(named))
    finally:
        named.context.close()
    bare = _webhooks(browser, "")
    try:
        bare_state = _selected(bare)
    finally:
        bare.context.close()
    bogus = _webhooks(browser, "&tab=nonsense")
    try:
        bogus_state = _selected(bogus)
    finally:
        bogus.context.close()

    testbase.assert_equal(
        (opened, back, again, bare_state, bogus_state),
        ((["Outbound"], "outbound"), (["Inbound"], "", True), (["Outbound"], "outbound"), ["Inbound"], ["Inbound"]),
    )
    return


def test_secrets_opens_on_the_scope_the_address_names_and_writes_changes_back(browser: Browser):
    """
    **Feature: tab in the address (ORC-27)**
    **Property: ``?scope=project`` opens the Project tab; a bare address and an unknown scope open
    Org; choosing User puts ``scope=user`` in the address and choosing Org removes it.**
    """
    named = _secrets(browser, "?scope=project")
    try:
        opened = (_selected(named), _query(named))
        named.locator('[data-role="scope-tab"][data-scope-kind="USER"]').click()
        named.wait_for_timeout(500)
        user = (_selected(named), _query(named))
        named.locator('[data-role="scope-tab"][data-scope-kind="ORG"]').click()
        named.wait_for_timeout(500)
        org = (_selected(named), _query(named))
    finally:
        named.context.close()
    bare = _secrets(browser, "")
    try:
        bare_state = _selected(bare)
    finally:
        bare.context.close()
    bogus = _secrets(browser, "?scope=nonsense")
    try:
        bogus_state = _selected(bogus)
    finally:
        bogus.context.close()

    testbase.assert_equal(
        (opened, user, org, bare_state, bogus_state),
        ((["Project"], "project"), (["User"], "user"), (["Org"], ""), ["Org"], ["Org"]),
    )
    return
