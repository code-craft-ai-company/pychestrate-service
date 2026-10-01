"""
.. module:: test_p32zzzzzzzzzzzzzzzzz_secrets_owner_in_the_address_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Secrets page keeps which project or user it is showing in the address (ORC-27).

.. moduleauthor:: Code Craft AI LLC

The Secrets tab was in the address (``?scope=project``) but the owner chosen inside it was not, so a shared link opened
the Project tab on its first project, whatever the sender was looking at. The address now carries the owner too
(``?scope=project&owner=<project id>``): it opens on that owner when the list offers it, writes the choice back, and
leaves it out for Org and when the owner is not one the person may see. The page is opened in a browser against stubbed
API answers.
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
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

FIRST: str = "0f6c2c1e-7777-4000-8000-00000000000a"
SECOND: str = "0f6c2c1e-7777-4000-8000-00000000000b"
PROJECTS = {"items": [
    {"project_id": FIRST, "display_name": "First", "slug": "first"},
    {"project_id": SECOND, "display_name": "Second", "slug": "second"},
], "meta": {"total": 2}}
EMPTY = {"items": [], "meta": {"total": 0}}


def _open(browser: Browser, query: str) -> Any:
    """Open Secrets; ``page.asked`` collects the (scope_kind, scope_ref) of each list request."""
    asked: List[Any] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-secrets-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/secrets": EMPTY, "/api/v1/identity/users": EMPTY},
    )

    def note(request: Any) -> None:
        parsed = urllib.parse.urlparse(request.url)
        if parsed.path == "/api/v1/secrets":
            params = dict(urllib.parse.parse_qsl(parsed.query))
            asked.append((params.get("scope_kind"), params.get("scope_ref")))

    context.on("request", note)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/secrets" + query)
    page.wait_for_selector('[data-role="scope-tab"]')
    page.wait_for_timeout(2000)
    page.asked = asked
    return page


def _query(page: Any) -> Dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def test_a_link_opens_on_the_owner_it_names_and_choosing_another_writes_it_back(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``?scope=project&owner=<second project>`` lists that project's secrets (not the first project's) and
    shows it in the owner list; choosing the first project writes ``owner=<first>``; switching to Org removes both the
    scope and the owner from the address.**
    """
    page = _open(browser, "?scope=project&owner=" + SECOND)
    try:
        asked = page.asked[-1]
        shown = page.locator('[data-role="scope-ref-select"]').evaluate("el => el.value")
        kept = _query(page)
        page.locator('[data-role="scope-ref-select"]').click()
        page.get_by_role("option", name="First", exact=True).click()
        page.wait_for_timeout(800)
        chosen = (page.asked[-1], _query(page).get("owner"))
        page.locator('[data-role="scope-tab"][data-scope-kind="ORG"]').click()
        page.wait_for_timeout(600)
        org = (_query(page).get("scope"), _query(page).get("owner"))
    finally:
        page.context.close()

    testbase.assert_equal(
        (asked, shown, kept.get("scope"), kept.get("owner"), chosen, org),
        (("PROJECT", SECOND), SECOND, "project", SECOND, (("PROJECT", FIRST), FIRST), (None, None)),
    )
    return


def test_an_owner_that_is_not_on_offer_falls_back_to_the_first_and_the_address_says_so(browser: Browser):
    """
    **Feature: view state in the address (ORC-27)**
    **Property: ``?scope=project&owner=<unknown id>`` lists the first project's secrets and the address is corrected to
    that project (it does not keep naming an owner that is not being shown); a bare ``?scope=project`` does the same
    and a link without ``owner`` keeps working.**
    """
    unknown = _open(browser, "?scope=project&owner=00000000-0000-4000-8000-000000000000")
    try:
        unknown_state = (unknown.asked[-1], _query(unknown).get("owner"))
    finally:
        unknown.context.close()
    bare = _open(browser, "?scope=project")
    try:
        bare_state = (bare.asked[-1], _query(bare).get("owner"))
    finally:
        bare.context.close()

    testbase.assert_equal((unknown_state, bare_state), ((("PROJECT", FIRST), FIRST), (("PROJECT", FIRST), FIRST)))
    return
