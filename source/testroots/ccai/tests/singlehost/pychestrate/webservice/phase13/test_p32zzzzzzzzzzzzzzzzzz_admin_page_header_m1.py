"""
.. module:: test_p32zzzzzzzzzzzzzzzzzz_admin_page_header_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The admin pages put their one action, Refresh, in the title row (ADM-30).

.. moduleauthor:: Code Craft AI LLC

The admin bundle pages (Administration, System Health, Extension Registry, Feature Flags) put a boxed "Refresh" button on
a row of its own under the title, which made every page look like a form with one control. The title now sits on the
left with Refresh on the right of the same row, as a quiet button (no box until it is hovered). The pages are opened in
a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 800}}

PAGES: List[Tuple[str, str]] = [
    ("Administration", "/admin"),
    ("System Health", "/admin/system-health"),
    ("Extension Registry", "/admin/extensions"),
    ("Feature Flags", "/admin/feature-flags"),
]


def _header(browser: Browser, path: str) -> Dict[str, Any]:
    page = open_shell_page(
        browser, path=path, bundle_names=["pyc-site-shell", "pyc-admin-bundle"],
        api_stubs={"/api/v1/flags": [], "/api/v1/projects": {"items": [], "meta": {"total": 0}}}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="refresh"]')
        page.wait_for_timeout(1000)
        heading = page.locator("h1.pyc-admin__heading").bounding_box()
        refresh = page.locator('[data-role="refresh"]').bounding_box()
        return {
            "text": page.locator("h1.pyc-admin__heading").inner_text(),
            "same_row": abs((heading["y"] + heading["height"] / 2) - (refresh["y"] + refresh["height"] / 2)) < 12,
            "refresh_on_the_right": refresh["x"] > heading["x"] + heading["width"],
            "variant": page.locator('[data-role="refresh"]').get_attribute("variant"),
        }
    finally:
        page.context.close()


def test_every_admin_page_has_the_title_and_a_quiet_refresh_on_one_row(browser: Browser):
    """
    **Feature: admin page header (ADM-30)**
    **Property: on each of the four admin pages the title and Refresh share a row (their vertical centres are
    within a few pixels), Refresh is to the right of the title, and it is the quiet (tertiary) button.**
    """
    found = {label: _header(browser, path) for label, path in PAGES}

    testbase.assert_equal(
        found,
        {label: {"text": label, "same_row": True, "refresh_on_the_right": True, "variant": "tertiary"} for label, _path in PAGES},
    )
    return
