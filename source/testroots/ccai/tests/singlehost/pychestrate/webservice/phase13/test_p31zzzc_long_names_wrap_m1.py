"""
.. module:: test_p31zzzc_long_names_wrap_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A very long name wraps inside its table cell (ADM-41).

.. moduleauthor:: Code Craft AI LLC

A 3,000-character display name broke the users table layout: an unbroken run of
characters widened the table past the page. Server-rendered tables now let a
long value wrap inside its cell. A page with such a name is opened in a browser
with the fragment stylesheet and the page's width is measured.
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
    open_fixture_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1024, "height": 768}}


def test_a_3000_character_name_does_not_widen_the_table_past_the_page(browser: Browser):
    """
    **Feature: long names (ADM-41)**
    **Property: a table cell holding one 3,000-character unbroken name wraps
    inside the table: the page has no horizontal overflow.**
    """
    body = (
        '<link rel="stylesheet" href="/static/styles/pyc-tokens.css"><link rel="stylesheet" href="/static/styles/pyc-fragment.css">'
        '<section class="pyc-admin-page-fragment"><div class="table-scroll"><table class="data-table"><thead><tr><th>Name</th><th>Email</th></tr></thead>'
        "<tbody><tr><td>" + "W" * 3000 + "</td><td>someone@example.com</td></tr></tbody></table></div></section>"
    )
    page = open_fixture_page(browser, body_html=body, **DESKTOP)
    try:
        page.wait_for_timeout(500)
        overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        table_inside = page.evaluate("() => document.querySelector('table').getBoundingClientRect().right <= window.innerWidth + 1")
    finally:
        page.context.close()

    testbase.assert_equal((overflow <= 0, table_inside), (True, True))
    return
