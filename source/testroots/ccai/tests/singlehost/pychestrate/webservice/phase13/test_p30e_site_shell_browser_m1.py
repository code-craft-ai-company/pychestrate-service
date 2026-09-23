"""
.. module:: test_p30e_site_shell_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Browser regressions for the site shell: the phone
               header, landmarks, the navigation drawer, the theme
               toggle, and the UI font.

.. moduleauthor:: Code Craft AI LLC

Each test renders the real shell document
(``site_shell/shell_document.html``) with the committed
``pyc-site-shell`` and ``pyc-mj-lib`` bundles in headless Chromium,
served in-process by :mod:`_shell_browser_harness` (no pychestrate
instance needed), and checks one property at a given viewport /
color scheme.

Covered audit findings: XC-02 (Sign out unreachable on phones),
LD-13 (serif palette font).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    DEEP_FOCUS_JS,
    RAW_CATALOG_KEYS_JS,
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


PHONE: Dict[str, Any] = {
    "viewport": {"width": 390, "height": 844},
    "has_touch": True,
    "is_mobile": True,
}
TABLET: Dict[str, Any] = {"viewport": {"width": 768, "height": 1024}}
DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

THEME_STORAGE_KEY: str = "pychestrate.ui.theme"
NAV_COLLAPSED_STORAGE_KEY: str = "pyc-site-shell.nav-collapsed"

LAYOUT_STATE_JS: str = (
    "() => { const layout = document.querySelector('mj-app-shell'); "
    "return {open: layout.hasAttribute('nav-open'), mode: layout.getAttribute('nav-mode')}; }"
)


def _right_edge(page: Any, selector: str) -> float:
    box = page.locator(selector).first.bounding_box()
    testbase.assert_true(box is not None, "{} is not rendered".format(selector))
    rtnval = box["x"] + box["width"]
    return rtnval


def _open_phone_drawer(page: Any) -> None:
    """
        Wait for the phone layout to settle into overlay mode, then
        open the drawer from the header toggle.
    """
    page.wait_for_function(
        "() => document.querySelector('mj-app-shell').getAttribute('nav-mode') === 'overlay'"
    )
    page.locator(".pyc-site-shell__nav-toggle").click()
    page.wait_for_function("() => document.querySelector('mj-app-shell').hasAttribute('nav-open')")
    return


# ---------------------------------------------------------------------------
# XC-02: the account controls fit on a phone
# ---------------------------------------------------------------------------


def test_phone_header_keeps_the_account_button_on_screen(browser: Browser):
    """
    **Feature: site shell -- phone header**
    **Property: at 390px the account button that holds Sign out sits
    inside the viewport.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        testbase.assert_true(page.locator(".pyc-site-shell__account-button").is_visible())
        testbase.assert_true(_right_edge(page, ".pyc-site-shell__account-button") <= 390)
    finally:
        page.context.close()
    return


def test_phone_account_menu_shows_sign_out_on_screen(browser: Browser):
    """
    **Feature: site shell -- phone header**
    **Property: at 390px, opening the account menu shows a Sign out
    control that lies inside the viewport.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        page.locator(".pyc-site-shell__account-button").click()
        sign_out = page.locator(".pyc-site-shell__logout-button")
        testbase.assert_true(sign_out.is_visible())
        testbase.assert_true(_right_edge(page, ".pyc-site-shell__logout-button") <= 390)
    finally:
        page.context.close()
    return


def test_phone_header_controls_stay_inside_the_viewport(browser: Browser):
    """
    **Feature: site shell -- phone header**
    **Property: at 390px no visible header control extends past the
    right edge of the viewport.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        overflow = page.evaluate(
            "() => Array.from(document.querySelectorAll('mj-app-bar a, mj-app-bar button, mj-app-bar mj-button'))"
            ".filter((el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')"
            ".filter((el) => el.getBoundingClientRect().right > window.innerWidth + 0.5)"
            ".map((el) => el.className || el.tagName)"
        )
        testbase.assert_equal(overflow, [])
    finally:
        page.context.close()
    return


def test_account_menu_escape_returns_focus_to_its_button(browser: Browser):
    """
    **Feature: site shell -- phone header**
    **Property: Escape closes the open account menu and returns focus
    to the account button.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        page.locator(".pyc-site-shell__account-button").click()
        page.keyboard.press("Escape")
        state = page.evaluate(
            "() => ({expanded: document.querySelector('.pyc-site-shell__account-button').getAttribute('aria-expanded'), "
            "focused: document.activeElement.classList.contains('pyc-site-shell__account-button')})"
        )
        testbase.assert_equal(state, {"expanded": "false", "focused": True})
    finally:
        page.context.close()
    return


def test_touch_devices_do_not_show_the_keyboard_shortcut(browser: Browser):
    """
    **Feature: site shell -- phone header**
    **Property: on a touch-first device (coarse pointer) the palette
    button shows no "Ctrl+K" shortcut text but stays available.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        hint = page.locator(".pyc-site-shell__palette-hint")
        visible_text = hint.inner_text().strip()
        testbase.assert_equal((visible_text, hint.is_visible()), ("", True))
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# LD-13: one UI typeface, overlays included
# ---------------------------------------------------------------------------


def test_body_uses_the_ui_font(browser: Browser):
    """
    **Feature: site shell -- typography**
    **Property: the document body uses the UI font stack (a sans-serif
    stack), not the browser's default serif.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        family = page.evaluate("() => getComputedStyle(document.body).fontFamily")
        testbase.assert_true("sans-serif" in family, family)
    finally:
        page.context.close()
    return


def test_command_palette_results_use_the_ui_font(browser: Browser):
    """
    **Feature: site shell -- typography**
    **Property: command-palette results, which mount on document.body,
    render in the UI font stack.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        page.evaluate("() => document.querySelector('pyc-site-shell').openPalette()")
        page.locator(".pyc-site-shell__palette-input").fill("Runs")
        page.wait_for_selector(".pyc-site-shell__palette-option-label")
        family = page.evaluate(
            "() => getComputedStyle(document.querySelector('.pyc-site-shell__palette-option-label')).fontFamily"
        )
        testbase.assert_true("sans-serif" in family, family)
    finally:
        page.context.close()
    return
