"""
.. module:: test_p31zzc_primary_button_contrast_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A primary mj-button has readable text in both themes (WCAG 1.4.3).

.. moduleauthor:: Code Craft AI LLC

The mj token pack keeps the text on the accent white in the dark theme, where
the accent is the light blue #4d83f7: 3.55:1, below the 4.5:1 of WCAG AA for
14px text. Every primary ``mj-button`` in the bundles (Save, Upsert, Add) was
flagged by axe (color-contrast) in the dark theme. The page's own dark is now
the text on the accent in both dark cases (the OS preference, and the explicit
choice); the light theme keeps white on the darker light-theme accent. A real
``mj-button`` is measured in a browser.
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

CONTRAST_JS: str = """async (theme) => {
    if (theme) { document.documentElement.setAttribute('data-theme', theme); }
    const button = document.createElement('mj-button');
    button.setAttribute('variant', 'primary');
    button.textContent = 'Save';
    document.body.appendChild(button);
    await new Promise((resolve) => setTimeout(resolve, 300));
    const inner = button.shadowRoot.querySelector('.btn');
    const style = getComputedStyle(inner);
    const parse = (text) => text.match(/[\\d.]+/g).slice(0, 3).map(Number);
    const luminance = ([r, g, b]) => {
        const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    };
    const fg = luminance(parse(style.color)), bg = luminance(parse(style.backgroundColor));
    const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
    return {ratio: Math.round(ratio * 100) / 100, color: style.color, background: style.backgroundColor};
}"""


def _ratio(browser: Browser, *, scheme: str, theme: Any) -> Dict[str, Any]:
    page = open_shell_page(browser, color_scheme=scheme, **DESKTOP)
    try:
        return page.evaluate(CONTRAST_JS, theme)
    finally:
        page.context.close()


def test_the_primary_button_text_reaches_4_5_to_1_in_every_theme(browser: Browser):
    """
    **Feature: primary button contrast (WCAG 1.4.3)**
    **Property: a primary mj-button's text is at least 4.5:1 against its
    background in the light theme, in the dark theme chosen explicitly, and
    in the dark theme the OS asks for.**
    """
    cases = {
        "light": _ratio(browser, scheme="light", theme=None),
        "dark, explicit": _ratio(browser, scheme="light", theme="dark"),
        "dark, from the OS": _ratio(browser, scheme="dark", theme=None),
    }

    testbase.assert_equal({name: result["ratio"] >= 4.5 for name, result in cases.items()},
                          {"light": True, "dark, explicit": True, "dark, from the OS": True})
    return
