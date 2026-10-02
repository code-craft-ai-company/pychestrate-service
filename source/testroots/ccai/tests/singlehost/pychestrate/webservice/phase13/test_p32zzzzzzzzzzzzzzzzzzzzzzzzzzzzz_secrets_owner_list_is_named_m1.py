"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzz_secrets_owner_list_is_named_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Secrets owner list has an accessible name (ADM-29).

.. moduleauthor:: Code Craft AI LLC

Scanning every navigation page on staging for controls without an accessible name found one: the drop-down that chooses which project or
user's secrets to show. It sat beside a visible caption but had no name of its own, so a screen reader announced an unlabelled combo
box. It is now named "Project" or "User" to match its tab. The page is opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1300, "height": 800}}

FIRST: str = "0f6c2c1e-7777-4000-8000-00000000000a"
PROJECTS = {"items": [{"project_id": FIRST, "display_name": "First", "slug": "first"}], "meta": {"total": 1}}
USERS = {"items": [{"user_id": "0f6c2c1e-8888-4000-8000-000000000001", "login_name": "ada", "display_name": "Ada Lovelace", "status": "active"}], "meta": {"total": 1}}


def test_the_owner_list_is_named_after_its_tab(browser: Browser):
    """
    **Feature: accessible names (ADM-29)**
    **Property: on the Project tab the owner drop-down's accessible name is "Project", and on the User tab it is "User"
    (read from the select's name, which the component draws visually hidden).**
    """
    names = {}
    for scope, owner in (("project", "Project"), ("user", "User")):
        page = open_shell_page(
            browser, path="/secrets?scope=" + scope, bundle_names=["pyc-site-shell", "pyc-secrets-bundle"],
            api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/secrets": [], "/api/v1/identity/users": USERS}, **DESKTOP,
        )
        try:
            page.wait_for_selector('[data-role="scope-ref-select"]')
            page.wait_for_timeout(1500)
            names[owner] = page.evaluate(
                """() => {
                    const select = document.querySelector('[data-role=scope-ref-select]');
                    const trigger = select.shadowRoot.querySelector('button.trigger');
                    const labelled = trigger.getAttribute('aria-labelledby');
                    const text = labelled ? (select.shadowRoot.getElementById(labelled).textContent || '').trim() : '';
                    return [select.getAttribute('label'), text];
                }"""
            )
        finally:
            page.context.close()

    testbase.assert_equal(names, {"Project": ["Project", "Project"], "User": ["User", "User"]})
    return
