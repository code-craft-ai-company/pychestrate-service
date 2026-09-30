"""
.. module:: test_p32y_release_component_labels_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Pychestrate Updates page names its components in words (ORC-17, ORG-F21).

.. moduleauthor:: Code Craft AI LLC

The release form took its component as free text and the table showed the API's identifiers ("agent"),
a word the product avoids for its pod client. The table and the detail now say "Pychestrate service" and
"Pod client" (the API values are still what is sent). Opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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


def _entry(channel_id: str, component: str) -> Dict[str, Any]:
    return {
        "channel_id": channel_id, "component": component, "version": "1.4.0", "channel": "stable", "status": "published",
        "rollout_fraction": 1.0, "artifact_uri": "oci://registry/x:1.4.0", "artifact_sha256": "ab" * 32, "issued_by": "release-bot",
        "issued_at": "2026-09-29T10:00:00Z",
    }


def test_components_are_named_in_words_in_the_table_and_the_detail(browser: Browser):
    """
    **Feature: plain component names (ORC-17)**
    **Property: a service release reads "Pychestrate service" and an agent release reads "Pod client"
    in the table and in the detail heading; the word "agent" is not on the page.**
    """
    entries: List[Dict[str, Any]] = [_entry("c1", "service"), _entry("c2", "agent")]
    stubs: Dict[str, Any] = {"/api/v1/release-channels": {"items": entries, "meta": {"total": 2}}}
    for entry in entries:
        stubs["/api/v1/release-channels/" + entry["channel_id"]] = entry
    page = open_shell_page(browser, path="/release-channels", bundle_names=["pyc-site-shell", "pyc-ops-bundle"], api_stubs=stubs, **DESKTOP)
    try:
        page.wait_for_selector('[data-role="show-release"]')
        page.wait_for_timeout(800)
        in_table = {name: page.get_by_text(name, exact=True).count() for name in ("Pychestrate service", "Pod client")}
        page.locator('[data-role="show-release"]').nth(1).click()
        page.wait_for_selector('[data-role="release-detail"]')
        heading = page.locator("h2", has_text="Published Release").inner_text()
        words = page.locator("main").inner_text()
    finally:
        page.context.close()

    testbase.assert_equal(
        (in_table, heading.startswith("Published Release"), any(name in heading for name in ("Pychestrate service", "Pod client")), "agent" in words.lower()),
        ({"Pychestrate service": 1, "Pod client": 1}, True, True, False),
    )
    return
