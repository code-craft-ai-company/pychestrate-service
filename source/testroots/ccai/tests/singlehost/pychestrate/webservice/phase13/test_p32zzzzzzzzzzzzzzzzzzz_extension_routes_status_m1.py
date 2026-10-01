"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzz_extension_routes_status_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Extension Registry says whether the extensions' routes are served, in words (ADM-30).

.. moduleauthor:: Code Craft AI LLC

The page showed the API's own word for the state of the extensions' routes ("Registry status: mounted" / "deferred"). A
person reading "deferred" cannot tell whether anything is wrong. The line now reads "Extension routes:" with "Serving",
"Not attached yet" (amber) or "Unknown", and the chip's hover text says what each means. The page is opened in a browser
against stubbed API answers.
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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 800}}

ROUTE = {
    "ext_name": "example", "full_path": "/api/v1/ext/example/echo", "required_permissions": [], "required_capabilities": [],
    "handler_class": "ExampleEcho", "mounted": True,
}


def _status(browser: Browser, dynamic_mount: Any) -> Dict[str, str]:
    body: Dict[str, Any] = {"items": [ROUTE], "total": 1}
    if dynamic_mount is not None:
        body["dynamic_mount"] = dynamic_mount
    page = open_shell_page(
        browser, path="/admin/extensions", bundle_names=["pyc-site-shell", "pyc-admin-bundle"], api_stubs={"/api/v1/ext": body}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="registry-status"]')
        page.wait_for_timeout(500)
        chip = page.locator('[data-role="registry-status"] mj-chip')
        return {
            "line": " ".join(page.locator('[data-role="registry-status"]').inner_text().split()),
            "tone": chip.get_attribute("data-tone") or "",
            "hint": chip.get_attribute("title") or "",
        }
    finally:
        page.context.close()


def test_the_extension_routes_state_is_said_in_words_with_its_meaning_on_hover(browser: Browser):
    """
    **Feature: extension routes status (ADM-30)**
    **Property: "mounted" reads "Extension routes: Serving" (green), "deferred" reads "Not attached yet" (amber) and
    says the routes are not served, a missing or odd value reads "Unknown"; no state shows the API's own word.**
    """
    mounted = _status(browser, "mounted")
    deferred = _status(browser, "deferred")
    unknown = _status(browser, None)

    testbase.assert_equal(
        (
            (mounted["line"], mounted["tone"]),
            (deferred["line"], deferred["tone"], "not being served" in deferred["hint"] or "not attached" in deferred["hint"]),
            (unknown["line"], unknown["tone"]),
        ),
        (
            ("Extension routes: Serving", "ok"),
            ("Extension routes: Not attached yet", "warn", True),
            ("Extension routes: Unknown", "error"),
        ),
    )
    return
