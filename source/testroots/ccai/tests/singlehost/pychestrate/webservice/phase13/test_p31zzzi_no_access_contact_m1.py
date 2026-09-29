"""
.. module:: test_p31zzzi_no_access_contact_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The no-access screen says whom to ask and offers a written request (XC-21).

.. moduleauthor:: Code Craft AI LLC

A person with no role saw "Ask an administrator to grant you a role" on every
page and nothing about who that is. When the installation names a contact the
shell now shows it: as a mail link with the request already written when it is
an address, as plain text otherwise. The dashboards editor's read-only notice
uses the same sentence. Without a contact the screen is what it was.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict, Tuple

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

OLD_TEXT: str = "Ask an administrator to grant you a role so you can use Pychestrate."


def _no_access_screen(browser: Browser, contact: str) -> Tuple[str, Any]:
    """
        Open the shell for a person who holds no permission at all.

        :returns: (the empty state's text, its ``request-access`` link's href or None)
    """
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell"],
        api_stubs={
            "/api/v1/me/permissions": {"permissions": []},
            "/api/v1/me/navigation": {"groups": [], "entries": []},
        },
        admin_contact=contact,
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    try:
        page.goto(FAKE_ORIGIN + "/")
        page.wait_for_selector("mj-empty-state")
        page.wait_for_timeout(500)
        text = page.locator("mj-empty-state").inner_text()
        link = page.locator('[data-role="request-access"]')
        href = link.get_attribute("href") if link.count() > 0 else None
    finally:
        context.close()
    return text, href


def test_an_address_gets_a_request_that_is_already_written(browser: Browser):
    """
    **Feature: whom to ask for access (XC-21)**
    **Property: with an email address as the contact the screen offers "Email
    <address> to request access", a mail link whose subject and body are
    filled in and name the person's account.**
    """
    text, href = _no_access_screen(browser, "ops@lab.example")
    parsed = urllib.parse.urlparse(href or "")
    query = urllib.parse.parse_qs(parsed.query)

    testbase.assert_equal(
        (OLD_TEXT in text, "Email ops@lab.example to request access" in text, parsed.scheme, parsed.path, query.get("subject"), "Please give my Pychestrate account a role" in "".join(query.get("body", []))),
        (True, True, "mailto", "ops@lab.example", ["Pychestrate access request"], True),
    )
    return


def test_another_contact_is_shown_as_it_is_written_and_none_changes_nothing(browser: Browser):
    """
    **Feature: whom to ask for access (XC-21)**
    **Property: a contact that is not an address (a team and channel) is shown
    in "To ask for access, contact ..." with no link; with no contact the
    screen holds only the original sentence.**
    """
    text_other, href_other = _no_access_screen(browser, "the Platform team (#help-pychestrate)")
    text_none, href_none = _no_access_screen(browser, "")

    testbase.assert_equal(
        ("To ask for access, contact the Platform team (#help-pychestrate)." in text_other, href_other, "To ask for access" in text_none, href_none, OLD_TEXT in text_none),
        (True, None, False, None, True),
    )
    return
