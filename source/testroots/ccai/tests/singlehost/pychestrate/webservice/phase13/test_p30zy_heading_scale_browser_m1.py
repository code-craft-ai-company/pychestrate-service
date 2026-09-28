"""
.. module:: test_p30zy_heading_scale_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One page-title style and one font stack across the server
               pages and the component-library pages (XC-05).

.. moduleauthor:: Code Craft AI LLC

The product read as two apps. A page title measured 28px/600 on a server
page, 18px/600 in a bundle (it used the brand-label size), 32px/700 on
the home page and 24px/700 on the error pages. The UI font stack
omitted ``system-ui`` while the component library's started with it, so
on Linux the two resolved to different faces on one screen.
``pyc-tokens.css`` now defines the heading scale and takes the library's
font token, and each page title uses them.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Tuple

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

#: The page title every page shows: 1.75rem at the 16px root, weight 600.
PAGE_TITLE: Tuple[str, str] = ("28px", "600")

TITLE_JS: str = r"""
(selector) => {
  const heading = document.querySelector(selector);
  if (heading === null) {
    return null;
  }
  const style = getComputedStyle(heading);
  return [style.fontSize, style.fontWeight];
}
"""

FRAGMENT_JS: str = r"""
() => {
  const main = document.querySelector('main.pyc-site-shell__main');
  const fragment = document.createElement('section');
  fragment.className = 'pyc-admin-page-fragment';
  fragment.innerHTML = '<div class="page-header"><h1 data-probe="server-title">Users</h1></div>';
  main.appendChild(fragment);
  return true;
}
"""

FONT_TOKENS_JS: str = r"""
() => {
  const root = getComputedStyle(document.documentElement);
  const norm = (value) => value.replace(/\s+/g, ' ').trim();
  return [norm(root.getPropertyValue('--pyc-font-family-ui')), norm(root.getPropertyValue('--mj-font-sans'))];
}
"""


def _title(page: Any, selector: str) -> Any:
    rtnval = page.evaluate(TITLE_JS, selector)
    return rtnval


def test_the_home_page_title_is_the_page_title_style(browser: Browser):
    """
    **Feature: type system (XC-05)**
    **Property: the home page's h1 is 28px / 600, not the browser default
    32px / 700.**
    """
    page = open_shell_page(browser, path="/", **DESKTOP)
    try:
        page.locator(".pyc-site-shell__home-heading").wait_for()
        testbase.assert_equal(tuple(_title(page, ".pyc-site-shell__home-heading")), PAGE_TITLE)
    finally:
        page.context.close()
    return


def test_the_not_found_page_title_is_the_page_title_style(browser: Browser):
    """
    **Feature: type system (XC-05)**
    **Property: the page-not-found h1 is 28px / 600.**
    """
    page = open_shell_page(browser, path="/no-such-page-anywhere", **DESKTOP)
    try:
        page.locator(".pyc-site-shell__not-found-heading").wait_for()
        testbase.assert_equal(tuple(_title(page, ".pyc-site-shell__not-found-heading")), PAGE_TITLE)
    finally:
        page.context.close()
    return


def test_a_server_page_title_is_the_page_title_style(browser: Browser):
    """
    **Feature: type system (XC-05)**
    **Property: a server-rendered page's .page-header h1 is 28px / 600.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        page.evaluate(FRAGMENT_JS)
        testbase.assert_equal(tuple(_title(page, "[data-probe=server-title]")), PAGE_TITLE)
    finally:
        page.context.close()
    return


def test_a_bundle_page_title_is_the_page_title_style(browser: Browser):
    """
    **Feature: type system (XC-05)**
    **Property: a component-library bundle's page title (the Runs page)
    is 28px / 600, the same as a server page, not the 18px brand size.**
    """
    page = open_shell_page(
        browser,
        path="/runs",
        bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        **DESKTOP,
    )
    try:
        page.locator(".pyc-runs-list__heading").wait_for()
        testbase.assert_equal(tuple(_title(page, ".pyc-runs-list__heading")), PAGE_TITLE)
    finally:
        page.context.close()
    return


def test_the_server_and_library_font_stacks_are_the_same(browser: Browser):
    """
    **Feature: type system (XC-05)**
    **Property: --pyc-font-family-ui resolves to the component library's
    --mj-font-sans stack, so both kinds of page use one face.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        ui_stack, library_stack = page.evaluate(FONT_TOKENS_JS)
        testbase.assert_equal(ui_stack, library_stack)
        testbase.assert_equal(ui_stack.startswith("system-ui"), True, ui_stack)
    finally:
        page.context.close()
    return
