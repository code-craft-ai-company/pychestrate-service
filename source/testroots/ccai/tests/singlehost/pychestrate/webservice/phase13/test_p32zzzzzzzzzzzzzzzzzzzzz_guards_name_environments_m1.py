"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzz_guards_name_environments_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The guards page names an environment, not its id (ORC-18).

.. moduleauthor:: Code Craft AI LLC

The Blast-Radius Guards table's Environment column printed the environment's id ("9a1b2c3d-..."), and the environment pickers
read "staging (9a1b2c3d)". An environment has a name that is unique in its project, so that is what the page says now; the
id stays in the hover text of the table cell. The page is opened in a browser against stubbed API answers.
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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT: str = "0f6c2c1e-1111-4000-8000-000000000001"
ENVIRONMENT: str = "9a1b2c3d-1111-4000-8000-0000000000e1"


def test_the_guards_table_and_pickers_say_the_environments_name(browser: Browser):
    """
    **Feature: names, not ids (ORC-18)**
    **Property: a guard on environment "staging" reads "staging" in the Environment column (its id only in the hover
    text), and the environment picker offers "staging", not "staging (9a1b2c3d)".**
    """
    page = open_shell_page(
        browser, path="/blast-radius-guards?project_id=" + PROJECT, bundle_names=["pyc-site-shell", "pyc-infra-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/projects/{}/environments".format(PROJECT): {"items": [{"environment_id": ENVIRONMENT, "name": "staging", "kind_name": "lab", "state": "active"}], "meta": {"total": 1}},
            "/api/v1/projects/{}/blast-radius-guards".format(PROJECT): {"items": [{
                "guard_id": ENVIRONMENT + ".max_changes", "project_id": PROJECT, "environment_id": ENVIRONMENT, "rule_id": "max_changes",
                "enabled": True, "added_at": "2026-09-29T10:00:00+00:00",
            }], "meta": {"total": 1}},
        },
        **DESKTOP,
    )
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(1500)
        cells = page.evaluate("""() => [...document.querySelector('mj-data-table').shadowRoot.querySelectorAll('span[title]')].map((el) => [el.textContent, el.getAttribute('title')])""")
        options = page.evaluate("() => [...document.querySelectorAll('[data-role=\"environment-filter\"] mj-option')].map((el) => el.textContent.trim())")
        table_text = " ".join(page.evaluate("() => document.querySelector('mj-data-table').shadowRoot.textContent").split())
    finally:
        page.context.close()

    testbase.assert_equal(
        ([cell for cell in cells if cell[1] == ENVIRONMENT], [option for option in options if option], ENVIRONMENT[:8] in table_text),
        ([["staging", ENVIRONMENT]], ["staging"], False),
    )
    return
