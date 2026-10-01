"""
.. module:: test_p32zz_access_contact_in_permission_messages_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A refused action says whom to ask for access (XC-21).

.. moduleauthor:: Code Craft AI LLC

About thirty bundle messages said "You do not have permission to ..." and none said what to do next; only
the dashboard editor named the installation's access contact. Every toast now adds "To ask for access, contact
<contact>." to a permission message when the installation names one (``PYCHESTRATE_ADMIN_CONTACT``), and never
invents a contact when it does not. A message that already says whom to ask is left as it is. Opened in a
browser against stubbed API answers, with the toggle refused as a person without the permission would be.
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
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-8888-4000-8000-000000000001"
WEBHOOK_ID: str = "0f6c2c1e-8888-4000-8000-000000000002"
PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
INTEGRATIONS = {
    "items": [{"webhook_id": WEBHOOK_ID, "project_id": PROJECT_ID, "provider": "github", "hook_name": "push", "enabled": False}],
    "meta": {"total": 1},
}


def _refused_toast(browser: Browser, *, contact: str) -> str:
    """Open Webhooks, press Enable on an integration whose change the API refuses (403), return the toast."""
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-ops-bundle"], admin_contact=contact,
        api_stubs={
            "/api/v1/projects": PROJECTS, "/api/v1/webhooks/in/integrations": INTEGRATIONS,
            "/api/v1/me/permissions": {"permissions": ["system:webhooks.write"]},
        },
    )

    def refuse(route: Any) -> None:
        if route.request.method == "PATCH":
            route.fulfill(status=403, headers={"Content-Type": "application/problem+json"}, body=b'{"title": "Forbidden", "status": 403}')
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/webhooks/in/integrations/.+"), refuse)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    try:
        page.goto(FAKE_ORIGIN + "/webhooks?project_id=" + PROJECT_ID)
        page.wait_for_selector('[data-role="integration-toggle"]', state="visible")
        page.wait_for_timeout(500)
        page.locator('[data-role="integration-toggle"]').first.click()
        page.wait_for_selector('[data-role="toast"][data-tone="error"]')
        return " ".join(page.locator('[data-role="toast"][data-tone="error"] .pyc-ops__toast-message').first.inner_text().split())
    finally:
        context.close()


def test_a_refused_action_says_whom_to_ask_when_the_installation_names_a_contact(browser: Browser):
    """
    **Feature: say whom to ask (XC-21)**
    **Property: with an access contact set the refusal toast reads "You do not have permission to ...
    To ask for access, contact <contact>."; with none set it is the bare permission message, with no contact
    invented.**
    """
    with_contact = _refused_toast(browser, contact="ops@lab.example")
    without = _refused_toast(browser, contact="")

    sentence = " To ask for access, contact ops@lab.example."
    testbase.assert_equal(
        (with_contact.startswith("You do not have permission to "), with_contact.endswith(sentence), without.startswith("You do not have permission to "), "contact" in without),
        (True, True, True, False),
    )
    return
