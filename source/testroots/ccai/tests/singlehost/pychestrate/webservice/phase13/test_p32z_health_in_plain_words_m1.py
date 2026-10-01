"""
.. module:: test_p32z_health_in_plain_words_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: System Health says what is healthy, and names its checks in words (ADM-30).

.. moduleauthor:: Code Craft AI LLC

The System Health page showed a bare "ok" chip (and "degraded", "error") beside checks named by their
identifiers (``envelope-signing-key``, ``client-certificate-proxies``). It now says Healthy, Needs attention
or Failing, and the checks carry a label for people (the identifier stays as the hover text). The admin
overview uses the same words. Opened in a browser against a stubbed health document.
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

HEALTH = {
    "status": "degraded", "version": "0.0.7-preview", "generated_at": "2026-09-29T10:00:00+00:00",
    "subsystems": [
        {"name": "database", "label": "Database", "status": "ok", "detail": "Request-scoped session attached."},
        {
            "name": "job-loop", "label": "Job Execution Loop", "status": "degraded", "detail": "Pods cannot receive jobs.",
            "backends": [
                {"name": "envelope-signing-key", "label": "Job signing key", "status": "degraded", "reason": "Not installed."},
                {"name": "enrollment-ca", "label": "Pod enrollment certificate authority", "status": "ok", "reason": "Installed."},
                {"name": "dispatch-transport", "status": "error", "reason": "Queue stopped."},
            ],
        },
    ],
}


def test_the_health_page_says_healthy_needs_attention_or_failing_and_names_its_checks(browser: Browser):
    """
    **Feature: health in plain words (ADM-30)**
    **Property: the overall, subsystem and per-check chips read "Needs attention", "Healthy" and "Failing"
    (never bare "ok", "degraded" or "error"); each check shows its label, with its identifier as hover text;
    a check with no label falls back to its identifier.**
    """
    page = open_shell_page(
        browser, path="/admin/system-health", bundle_names=["pyc-site-shell", "pyc-admin-bundle"],
        api_stubs={"/api/v1/system/health": HEALTH}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="subsystem-card"]')
        page.wait_for_timeout(1000)
        # The per-check chips are drawn inside the table's own shadow root: read them through Playwright.
        chips = [text.strip() for text in page.locator("mj-chip").all_inner_texts()]
        checks = page.get_by_text("Job signing key", exact=True)
        title = checks.first.get_attribute("title")
        names = {
            label: page.get_by_text(label, exact=True).count()
            for label in ("Job signing key", "Pod enrollment certificate authority", "dispatch-transport")
        }
        bare = [word for word in ("ok", "degraded", "error") if word in chips]
    finally:
        page.context.close()

    testbase.assert_equal(
        (sorted(set(chips)), bare, title, names),
        (["Failing", "Healthy", "Needs attention"], [], "envelope-signing-key", {"Job signing key": 1, "Pod enrollment certificate authority": 1, "dispatch-transport": 1}),
    )
    return
