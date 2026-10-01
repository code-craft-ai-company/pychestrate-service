"""
.. module:: test_p32zzzzzzz_section_headings_share_one_size_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Section headings are the same size in bundle and server pages (XC-05).

.. moduleauthor:: Code Craft AI LLC

Page titles were unified earlier. A *section* heading was still not: a server-rendered card heading is
16px / 600 while a bundle's was 14px in some views (run detail, admin overview, updates detail) and 16px in
others. Every bundle section, panel and sub heading now takes the ``--pyc-font-size-h3`` token (16px), the same
as the server's. A source guard checks every bundle stylesheet; a browser check measures one rendered heading.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Any, Dict, List

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

ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir,
    "site", "ccai", "pychestrate", "webservice", "webinterface", "static", "javascript",
)


def test_every_bundle_section_heading_rule_uses_the_h3_token():
    """
    **Feature: one type system (XC-05)**
    **Property: every rule for a ``__section-heading``, ``__subheading`` or ``__panel-heading`` class in a
    bundle stylesheet sets its size from ``--pyc-font-size-h3`` and none from the body or small tokens.**
    """
    wrong: List[str] = []
    seen = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "pyc-*-bundle", "pyc-*-bundle.css"))):
        source = open(path, encoding="utf-8").read()
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", source):
            selector, body = match.group(1), match.group(2)
            if re.search(r"\.pyc-[a-z-]+__(?:section-heading|subheading|panel-heading)\b", selector) is None:
                continue
            seen += 1
            size = re.search(r"font-size:\s*([^;]+);", body)
            if size is None or "--pyc-font-size-h3" not in size.group(1):
                wrong.append(os.path.basename(path) + ": " + " ".join(selector.split()))

    testbase.assert_equal((wrong, seen >= 10), ([], True))
    return


def test_a_rendered_bundle_section_heading_is_sixteen_pixels_and_semibold(browser: Browser):
    """
    **Feature: one type system (XC-05)**
    **Property: the Published Release heading on the Pychestrate Updates page (a bundle section heading that
    was 14px) renders at 16px and weight 600, like a server-rendered card heading.**
    """
    entry = {
        "channel_id": "c1", "component": "service", "version": "1.4.0", "channel": "stable", "status": "published", "rollout_fraction": 1.0,
        "artifact_uri": "oci://registry/x:1.4.0", "artifact_sha256": "ab" * 32, "issued_by": "release-bot", "issued_at": "2026-09-29T10:00:00Z",
    }
    page = open_shell_page(
        browser, path="/release-channels", bundle_names=["pyc-site-shell", "pyc-ops-bundle"],
        api_stubs={"/api/v1/release-channels": {"items": [entry], "meta": {"total": 1}}, "/api/v1/release-channels/c1": entry}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="show-release"]')
        page.wait_for_timeout(600)
        page.locator('[data-role="show-release"]').first.click()
        page.wait_for_selector('[data-role="release-detail"]')
        measured = page.evaluate("() => { const h = [...document.querySelectorAll('h2')].find((e) => e.textContent.startsWith('Published Release')); const s = getComputedStyle(h); return [s.fontSize, s.fontWeight]; }")
    finally:
        page.context.close()

    testbase.assert_equal(tuple(measured), ("16px", "600"))
    return
