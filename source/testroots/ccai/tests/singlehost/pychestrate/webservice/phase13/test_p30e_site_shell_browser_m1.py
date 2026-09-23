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
LD-13 (serif palette font), XC-03 (nested main landmarks, raw
landmark names, empty landmarks), XC-26 (drawer open over the
content at tablet width, focus not trapped, Escape), XC-13 (theme
toggle one click behind, theme applied after first paint).
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


def _open_account_menu(page: Any) -> None:
    """
        Open the account menu (it holds the theme control and Sign out
        at every width).
    """
    page.locator(".pyc-site-shell__account-button").click()
    page.wait_for_function(
        "() => document.querySelector('.pyc-site-shell__account-panel').hasAttribute('data-open')"
    )
    return


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


# ---------------------------------------------------------------------------
# XC-03: one main landmark, named navigation, no empty landmarks
# ---------------------------------------------------------------------------


def test_shell_page_exposes_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks**
    **Property: a shell page exposes exactly one main landmark (none
    nested inside another).**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        testbase.assert_equal(page.get_by_role("main").count(), 1)
    finally:
        page.context.close()
    return


def test_shell_sidebar_is_one_navigation_landmark_named_primary(browser: Browser):
    """
    **Feature: site shell -- landmarks**
    **Property: the sidebar is a single navigation landmark named
    "Primary" (not wrapped in a second navigation landmark).**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        names = page.evaluate(
            "() => { const out = []; const walk = (root) => { for (const el of root.querySelectorAll('*')) { "
            "if ((el.tagName === 'NAV' || el.getAttribute('role') === 'navigation') && el.checkVisibility()) "
            "out.push(el.getAttribute('aria-label')); if (el.shadowRoot) walk(el.shadowRoot); } }; "
            "walk(document); return out; }"
        )
        testbase.assert_equal(names.count("Primary"), 1)
        testbase.assert_equal(page.get_by_role("navigation", name="Primary", exact=True).count(), 1)
    finally:
        page.context.close()
    return


def test_shell_navigation_landmarks_are_not_named_by_catalog_keys(browser: Browser):
    """
    **Feature: site shell -- landmarks**
    **Property: no navigation landmark on a shell page is named by a
    raw "mj.*" catalog key.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        count = page.get_by_role("navigation", name=re.compile(r"mj\.")).count()
        testbase.assert_equal(count, 0)
    finally:
        page.context.close()
    return


def test_shell_page_has_no_empty_complementary_or_contentinfo(browser: Browser):
    """
    **Feature: site shell -- landmarks**
    **Property: the unused inspector and status-bar regions expose no
    complementary or contentinfo landmark.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        counts = (page.get_by_role("complementary").count(), page.get_by_role("contentinfo").count())
        testbase.assert_equal(counts, (0, 0))
    finally:
        page.context.close()
    return


def test_shell_page_shows_no_raw_catalog_keys(browser: Browser):
    """
    **Feature: site shell -- landmarks**
    **Property: no text or aria-label on a shell page (shadow DOM
    included) is a raw "mj.<component>.<key>" string.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        testbase.assert_equal(page.evaluate(RAW_CATALOG_KEYS_JS), [])
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# XC-26: the navigation drawer on tablets and phones
# ---------------------------------------------------------------------------


def test_tablet_width_starts_with_the_drawer_closed(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: at 768px the sidebar is an overlay drawer that starts
    closed, so it does not cover the page on load.**
    """
    page = open_shell_page(browser, **TABLET)
    try:
        page.wait_for_function(
            "() => document.querySelector('mj-app-shell').getAttribute('nav-mode') === 'overlay'"
        )
        testbase.assert_equal(page.evaluate(LAYOUT_STATE_JS), {"open": False, "mode": "overlay"})
    finally:
        page.context.close()
    return


def test_nav_toggle_reports_the_closed_drawer(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: at 768px the header's navigation toggle reports
    aria-expanded="false" for the closed drawer.**
    """
    page = open_shell_page(browser, **TABLET)
    try:
        page.wait_for_function(
            "() => document.querySelector('mj-app-shell').getAttribute('nav-mode') === 'overlay'"
        )
        expanded = page.get_attribute(".pyc-site-shell__nav-toggle", "aria-expanded")
        testbase.assert_equal(expanded, "false")
    finally:
        page.context.close()
    return


def test_phone_drawer_keeps_tab_inside_the_drawer(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: with the drawer open at 390px, Tab never moves focus
    out of the sidebar.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        _open_phone_drawer(page)
        outside = []
        for _ in range(6):
            page.keyboard.press("Tab")
            focus = page.evaluate(DEEP_FOCUS_JS)
            if focus is None or focus["inSidebar"] is False:
                outside.append(focus)
        testbase.assert_equal(outside, [])
    finally:
        page.context.close()
    return


def test_escape_closes_the_drawer_when_focus_is_on_the_page(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: Escape closes the open drawer even when focus is not
    inside it.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        _open_phone_drawer(page)
        page.evaluate("() => document.activeElement.blur()")
        page.keyboard.press("Escape")
        testbase.assert_equal(page.evaluate(LAYOUT_STATE_JS)["open"], False)
    finally:
        page.context.close()
    return


def test_closing_the_drawer_updates_the_toggle_state(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: after Escape closes the drawer, the header toggle
    reports aria-expanded="false" again.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        _open_phone_drawer(page)
        page.keyboard.press("Escape")
        expanded = page.get_attribute(".pyc-site-shell__nav-toggle", "aria-expanded")
        testbase.assert_equal(expanded, "false")
    finally:
        page.context.close()
    return


def test_phone_drawer_does_not_change_the_desktop_sidebar_preference(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: opening and closing the phone drawer with the toggle
    does not record a collapsed-sidebar preference.**
    """
    page = open_shell_page(browser, **PHONE)
    try:
        _open_phone_drawer(page)
        # The open drawer covers the toggle; activate it the way a
        # keyboard or assistive-technology user would.
        page.evaluate("() => document.querySelector('.pyc-site-shell__nav-toggle').click()")
        stored = page.evaluate(
            "(key) => window.localStorage.getItem(key)", NAV_COLLAPSED_STORAGE_KEY
        )
        testbase.assert_true(stored != "true", "overlay toggling stored nav-collapsed={}".format(stored))
    finally:
        page.context.close()
    return


def test_desktop_starts_with_the_sidebar_open(browser: Browser):
    """
    **Feature: site shell -- navigation drawer**
    **Property: at 1440px the sidebar is a static column and starts
    open.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        state = page.evaluate(LAYOUT_STATE_JS)
        testbase.assert_equal(state["open"], True)
        testbase.assert_true(state["mode"] != "overlay", "desktop layout is in overlay mode")
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# XC-09: the account menu at every width
# ---------------------------------------------------------------------------


def test_desktop_header_shows_the_display_name_on_the_account_button(browser: Browser):
    """
    **Feature: site shell -- account menu**
    **Property: at desktop width the header shows the user's display
    name (not the login name) on the account button, and the menu stays
    closed until opened.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        name = page.locator(".pyc-site-shell__account-button-name").text_content().strip()
        testbase.assert_equal(
            (page.locator(".pyc-site-shell__account-button").is_visible(), name,
             page.locator(".pyc-site-shell__logout-button").is_visible()),
            (True, "Ada Admin", False),
        )
    finally:
        page.context.close()
    return


def test_desktop_account_menu_holds_the_account_actions(browser: Browser):
    """
    **Feature: site shell -- account menu**
    **Property: opening the account menu at desktop width shows who is
    signed in (display and login name), Preferences, API tokens, the
    theme control and Sign out.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        _open_account_menu(page)
        panel = page.locator(".pyc-site-shell__account-panel")
        testbase.assert_equal(
            (panel.locator(".pyc-site-shell__user-menu-name").text_content().strip(),
             panel.get_by_role("link", name="Preferences").is_visible(),
             panel.get_by_role("link", name="API tokens").get_attribute("href"),
             page.locator(".pyc-site-shell__theme-toggle").is_visible(),
             page.locator(".pyc-site-shell__logout-button").is_visible()),
            ("Signed in as Ada Admin (admin)", True, "/account/api-tokens", True, True),
        )
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# XC-13: the theme toggle
# ---------------------------------------------------------------------------


def test_first_theme_click_after_an_os_dark_load_switches_to_light(browser: Browser):
    """
    **Feature: site shell -- theme**
    **Property: when the page loaded dark from the OS preference, the
    first click on the theme control switches it to light.**
    """
    page = open_shell_page(browser, color_scheme="dark", **DESKTOP)
    try:
        _open_account_menu(page)
        page.locator(".pyc-site-shell__theme-toggle").click()
        theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        testbase.assert_equal(theme, "light")
    finally:
        page.context.close()
    return


def test_theme_control_names_the_current_theme(browser: Browser):
    """
    **Feature: site shell -- theme**
    **Property: the theme control states the theme on screen ("Theme:
    Dark" after an OS-dark load).**
    """
    page = open_shell_page(browser, color_scheme="dark", **DESKTOP)
    try:
        label = page.locator(".pyc-site-shell__theme-toggle").text_content().strip()
        testbase.assert_equal(label, "Theme: Dark")
    finally:
        page.context.close()
    return


def test_stored_theme_is_applied_before_the_shell_script_runs(browser: Browser):
    """
    **Feature: site shell -- theme**
    **Property: a stored theme choice is on <html> even when the shell
    bundle has not run (applied from <head>, before the first
    paint).**
    """
    context_options = dict(DESKTOP)
    context_options["color_scheme"] = "light"
    page = open_shell_page(
        browser,
        blocked_paths=["/static/javascript/pyc-site-shell/index.js"],
        wait_for_ready=False,
        **context_options
    )
    try:
        page.evaluate("(key) => window.localStorage.setItem(key, 'dark')", THEME_STORAGE_KEY)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        testbase.assert_equal(theme, "dark")
    finally:
        page.context.close()
    return
