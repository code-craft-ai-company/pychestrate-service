"""
.. module:: test_p30u_flash_notice_contrast_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Flash messages stay readable in every theme (ADM-12).

.. moduleauthor:: Code Craft AI LLC

The shell lifts server flash messages into ``<mj-alert>`` notices. The
component library's OS-preference dark block flips the alert text to
near-white but left the status surfaces at their pale light values,
so with the "system" theme on a dark OS every error and success
message read at about 1.07:1. ``pyc-tokens.css`` now completes that
block.
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

#: WCAG 2.x AA minimum for normal-size text.
MINIMUM_CONTRAST: float = 4.5

THEME_STORAGE_KEY: str = "pychestrate.ui.theme"

#: JS: render one flash notice per severity the way the shell does and
#: return the WCAG contrast ratio of each one's text on its surface.
ALERT_CONTRAST_JS: str = r"""
async () => {
  await customElements.whenDefined('mj-alert');
  const parse = (value) => {
    const nums = (value.match(/[\d.]+/g) || []).map(Number);
    if (nums.length === 3) {
      nums.push(1);
    }
    return nums;
  };
  const blend = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat([1]);
  const channel = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const luminance = (rgb) => 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  const page = blend(parse(getComputedStyle(document.body).backgroundColor), [255, 255, 255, 1]);
  const out = {};
  for (const severity of ['info', 'success', 'warning', 'error']) {
    const notice = document.createElement('mj-alert');
    notice.setAttribute('severity', severity);
    notice.setAttribute('dismissible', '');
    notice.setAttribute('open', '');
    notice.classList.add('pyc-site-shell__flash-notice');
    const message = document.createElement('span');
    message.classList.add('pyc-site-shell__flash-notice-message');
    message.textContent = 'Could not save the variable.';
    notice.appendChild(message);
    document.body.appendChild(notice);
  }
  await new Promise((resolve) => setTimeout(resolve, 400));
  for (const notice of document.querySelectorAll('mj-alert.pyc-site-shell__flash-notice')) {
    const box = getComputedStyle(notice.shadowRoot.querySelector('.container'));
    const surface = blend(parse(box.backgroundColor), page);
    const text = blend(parse(box.color), surface);
    const hi = Math.max(luminance(text), luminance(surface));
    const lo = Math.min(luminance(text), luminance(surface));
    out[notice.getAttribute('severity')] = Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  }
  return out;
}
"""


def _alert_contrasts(browser: Browser, *, color_scheme: str, stored_theme: str) -> Dict[str, float]:
    """
        Contrast ratio of each severity's flash notice for one theme
        path: the OS colour scheme plus the shell's stored theme choice
        (``""`` is the "system" choice, which leaves data-theme unset).
    """
    page = open_shell_page(browser, color_scheme=color_scheme, wait_for_ready=False, **DESKTOP)
    try:
        page.evaluate(
            "(args) => { try { if (args.theme) { localStorage.setItem(args.key, args.theme); }"
            " else { localStorage.removeItem(args.key); } } catch (e) {} }",
            {"key": THEME_STORAGE_KEY, "theme": stored_theme},
        )
        page.reload()
        page.wait_for_function(
            "() => { const shell = document.querySelector('pyc-site-shell'); "
            "return shell !== null && shell.isReady === true; }"
        )
        rtnval = page.evaluate(ALERT_CONTRAST_JS)
    finally:
        page.context.close()
    return rtnval


def _unreadable(contrasts: Dict[str, float]) -> Dict[str, float]:
    rtnval = {severity: ratio for severity, ratio in contrasts.items() if ratio < MINIMUM_CONTRAST}
    return rtnval


def test_flash_notices_are_readable_under_the_os_dark_preference(browser: Browser):
    """
    **Feature: flash message contrast (ADM-12)**
    **Property: with the "system" theme on a dark OS (no data-theme
    attribute), every flash severity meets 4.5:1.**
    """
    contrasts = _alert_contrasts(browser, color_scheme="dark", stored_theme="")
    testbase.assert_equal(_unreadable(contrasts), {}, str(contrasts))
    return


def test_flash_notices_are_readable_in_the_explicit_dark_theme(browser: Browser):
    """
    **Feature: flash message contrast (ADM-12)**
    **Property: with the dark theme chosen in the header, every flash
    severity meets 4.5:1.**
    """
    contrasts = _alert_contrasts(browser, color_scheme="light", stored_theme="dark")
    testbase.assert_equal(_unreadable(contrasts), {}, str(contrasts))
    return


def test_flash_notices_are_readable_in_the_light_theme(browser: Browser):
    """
    **Feature: flash message contrast (ADM-12)**
    **Property: in the light theme every flash severity meets 4.5:1.**
    """
    contrasts = _alert_contrasts(browser, color_scheme="light", stored_theme="")
    testbase.assert_equal(_unreadable(contrasts), {}, str(contrasts))
    return
