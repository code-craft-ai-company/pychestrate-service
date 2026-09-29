"""
.. module:: test_p31zzx_admin_pages_finished_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The admin bundle pages explain themselves (ADM-30).

.. moduleauthor:: Code Craft AI LLC

The System Health page printed its time as raw ISO text
("2026-09-29T19:49:03.089833+00:00"), cut a health check's reason off after
sixteen characters, and the Feature Flags page said only "No feature flags
registered." The time now reads as everywhere else ("Checked 2026-09-29 12:49
PDT"), the reason column is wide enough for a real reason, and the empty flags
page says what a flag is and where one comes from. The pages are opened in a
browser against stubbed API answers.
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
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

LONG_REASON = "Installed (key_id=staging-envelope-ed25519, algorithm=ed25519, rotated 2026-09-01)"

HEALTH = {
    "status": "ok",
    "generated_at": "2026-09-29T19:49:03.089833+00:00",
    "subsystems": [
        {
            "name": "Job Execution Loop", "status": "ok", "detail": "Pods can enroll, receive signed jobs and upload results.",
            "backends": [{"name": "envelope-signing-key", "status": "ok", "reason": LONG_REASON}],
        },
    ],
}


def test_the_health_time_reads_like_every_other_time_and_a_reason_is_not_cut_off(browser: Browser):
    """
    **Feature: admin pages that explain themselves (ADM-30)**
    **Property: the health page's time is "Checked YYYY-MM-DD HH:MM zone", not
    ISO text with microseconds, and the whole of a health check's reason is
    inside its table (the column is wide enough).**
    """
    page = open_shell_page(browser, path="/admin/system-health", bundle_names=["pyc-site-shell", "pyc-admin-bundle"], api_stubs={"/api/v1/system/health": HEALTH}, **DESKTOP)
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(800)
        text = " ".join(page.locator("pyc-system-health").inner_text().split())
        reason_column_width = page.evaluate("() => document.querySelector('mj-data-table').columns.find((c) => c.key === 'reason').width")
    finally:
        page.context.close()

    checked = re.search(r"Checked (\S+ \S+ \S+)", text)
    testbase.assert_equal(
        (bool(checked) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+", checked.group(1)) is not None, "T19:49" in text, "Generated" in text, reason_column_width),
        (True, False, False, "44rem"),
    )
    return


def test_an_empty_flags_page_says_what_a_flag_is_and_where_one_comes_from(browser: Browser):
    """
    **Feature: admin pages that explain themselves (ADM-30)**
    **Property: with no flags the page explains that a flag switches an
    optional behaviour on or off without a release and that flags come from the
    REST API or an extension.**
    """
    page = open_shell_page(browser, path="/admin/feature-flags", bundle_names=["pyc-site-shell", "pyc-admin-bundle"], api_stubs={"/api/v1/flags": []}, **DESKTOP)
    try:
        page.wait_for_selector('[data-role="empty-state"]')
        text = " ".join(page.locator('[data-role="empty-state"]').inner_text().split())
    finally:
        page.context.close()

    testbase.assert_equal(
        ("switches an optional behaviour on or off without a release" in text, "POST /api/v1/flags" in text, "extension" in text),
        (True, True, True),
    )
    return
