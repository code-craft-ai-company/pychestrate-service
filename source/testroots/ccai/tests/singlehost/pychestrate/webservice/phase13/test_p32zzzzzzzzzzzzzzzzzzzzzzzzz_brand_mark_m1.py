"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzz_brand_mark_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One brand colour and a mark shared by the favicon, the header and the sign-in page (XC-24).

.. moduleauthor:: Code Craft AI LLC

The product had a plain-text name in the header, nothing on the sign-in page and a teal favicon (``#0e6b86``) whose colour appeared
nowhere else. The brand colour is now the interface's own accent blue (``--pyc-color-accent``): the favicon is drawn in it, and the
same mark stands beside the name in the shell header and above the sign-in form. The header is opened in a browser in both themes;
the sign-in page is rendered in process.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1200, "height": 400}}


def _static(*parts: str) -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "source", "site")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return os.path.join(current, "source", "site", "ccai", "pychestrate", "webservice", "webinterface", "static", *parts)


def test_the_favicon_is_drawn_in_the_interface_accent_colour():
    """
    **Feature: brand identity (XC-24)**
    **Property: the favicon's fill is exactly the accent colour the stylesheet tokens define for light mode, so the tab, the
    header and the buttons share one colour (the old teal is gone).**
    """
    with open(_static("favicon.svg"), encoding="utf-8") as handle:
        favicon = handle.read()
    with open(_static("styles", "pyc-tokens.css"), encoding="utf-8") as handle:
        tokens = handle.read()
    accent = re.search(r"--pyc-color-accent:\s*(#[0-9a-fA-F]{6})", tokens).group(1).lower()
    fills = re.findall(r'fill="(#[0-9a-fA-F]{6})"', favicon)

    testbase.assert_equal((accent in [fill.lower() for fill in fills], "#0e6b86" in favicon), (True, False))
    return


def test_the_shell_header_shows_the_mark_beside_the_name_in_both_themes(browser: Browser):
    """
    **Feature: brand identity (XC-24)**
    **Property: in light and dark themes the header's home link holds the mark (an image that has loaded, with empty alt text
    so it is not read twice) and the product name; the link is still named "Pychestrate home".**
    """
    results = {}
    for scheme in ("light", "dark"):
        page = open_shell_page(browser, path="/", bundle_names=["pyc-site-shell"], api_stubs={}, color_scheme=scheme, **DESKTOP)
        try:
            page.wait_for_selector(".pyc-site-shell__brand-link img")
            page.wait_for_timeout(500)
            results[scheme] = page.evaluate(
                """() => {
                    const link = document.querySelector('.pyc-site-shell__brand-link');
                    const mark = link.querySelector('img');
                    return {
                        loaded: mark.complete && mark.naturalWidth > 0, alt: mark.getAttribute('alt'), src: mark.getAttribute('src'),
                        name: link.querySelector('.pyc-site-shell__brand-name').textContent, label: link.getAttribute('aria-label'),
                        height: Math.round(mark.getBoundingClientRect().height),
                    };
                }"""
            )
        finally:
            page.context.close()

    expected = {"loaded": True, "alt": "", "src": "/static/favicon.svg", "name": "Pychestrate", "label": "Pychestrate home", "height": 22}
    testbase.assert_equal(results, {"light": expected, "dark": expected})
    return


def test_the_sign_in_page_carries_the_mark():
    """
    **Feature: brand identity (XC-24)**
    **Property: the sign-in page shows the mark (the favicon, decorative) above the product name, and the file it names is
    served.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm

    login = adm.get(path="/login")
    favicon = adm.get(path="/static/favicon.svg")

    testbase.assert_equal(
        (login.status_code, 'class="login-mark" src="/static/favicon.svg" alt=""' in login.text, favicon.status_code, "#2563eb" in favicon.text),
        (200, True, 200, True),
    )
    return
