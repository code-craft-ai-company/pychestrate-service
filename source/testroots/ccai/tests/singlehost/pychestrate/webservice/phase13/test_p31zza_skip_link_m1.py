"""
.. module:: test_p31zza_skip_link_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The "Skip to main content" link has a target that exists (WCAG 2.4.1).

.. moduleauthor:: Code Craft AI LLC

The link pointed at ``#pyc-main-content``, and the shell gave ``<main>`` that id
only inside the link's own click handler, so on every page the target did not
exist until the link had been used once; a checker (axe: "skip-link target
should exist") flagged every page, and the link did nothing from a URL
fragment. The id (and ``tabindex="-1"``) is now set when the main region is
built, and the keyboard path is checked end to end.
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


def test_the_skip_links_target_exists_before_the_link_is_used(browser: Browser):
    """
    **Feature: skip link (WCAG 2.4.1)**
    **Property: on load, the skip link's target element exists, is the
    main region and can take focus (tabindex -1).**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        found = page.evaluate(
            """() => {
                const link = document.querySelector('.pyc-site-shell__skip-link');
                const target = document.querySelector(link.getAttribute('href'));
                return {href: link.getAttribute('href'), exists: target !== null,
                        is_main: target !== null && target.tagName === 'MAIN',
                        tabindex: target !== null ? target.getAttribute('tabindex') : null};
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(found, {"href": "#pyc-main-content", "exists": True, "is_main": True, "tabindex": "-1"})
    return


def test_tab_then_enter_moves_focus_to_the_main_region(browser: Browser):
    """
    **Feature: skip link (WCAG 2.4.1)**
    **Property: the first Tab focuses the skip link, and Enter moves focus to
    the main region, so a keyboard user gets past the header and sidebar.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        page.keyboard.press("Tab")
        first = page.evaluate("document.activeElement.className")
        page.keyboard.press("Enter")
        landed = page.evaluate("document.activeElement.tagName + '#' + document.activeElement.id")
    finally:
        page.context.close()

    testbase.assert_equal((first, landed), ("pyc-site-shell__skip-link", "MAIN#pyc-main-content"))
    return
