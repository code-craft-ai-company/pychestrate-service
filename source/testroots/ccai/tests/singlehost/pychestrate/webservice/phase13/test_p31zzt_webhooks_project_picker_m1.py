"""
.. module:: test_p31zzt_webhooks_project_picker_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Webhooks page picks a project by name, not by pasted id (ORC-18).

.. moduleauthor:: Code Craft AI LLC

The Webhooks page asked for a raw project UUID before it would show anything.
It now lists the projects the person can see (as every other bundle page
does), selects the one named in the address or else the first, and loads that
project's integrations at once. When the projects cannot be listed it falls
back to the id field, and its prompts say "Enter a project id" only then. The
page is opened in a browser against stubbed API answers and the requests it
makes are recorded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict, List, Optional

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

DEMO_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
LAB_ID: str = "0f6c2c1e-6666-4000-8000-000000000002"

TWO_PROJECTS = {
    "items": [
        {"project_id": DEMO_ID, "display_name": "Demo", "slug": "demo"},
        {"project_id": LAB_ID, "display_name": "Lab", "slug": "lab"},
    ],
    "meta": {"total": 2},
}


def _open(browser: Browser, *, path: str, projects: Optional[Dict[str, Any]]) -> Any:
    """Open the Webhooks page; return (page, the project ids its integrations requests carried)."""
    seen: List[str] = []
    context = browser.new_context(**DESKTOP)
    stubs: Dict[str, Any] = {"/api/v1/webhooks/in/integrations": {"items": [], "meta": {"total": 0}}}
    if projects is not None:
        stubs["/api/v1/projects"] = projects
    install_site_routes(context, bundle_names=["pyc-site-shell", "pyc-ops-bundle"], api_stubs=stubs)

    def note(request: Any) -> None:
        parsed = urllib.parse.urlparse(request.url)
        if parsed.path == "/api/v1/webhooks/in/integrations":
            seen.append(urllib.parse.parse_qs(parsed.query).get("project_id", [""])[0])

    context.on("request", note)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    page.wait_for_selector('pyc-webhooks [data-role="project-region"]')
    page.wait_for_timeout(1200)
    return page, seen


def test_the_page_lists_the_projects_selects_the_first_and_loads_its_integrations(browser: Browser):
    """
    **Feature: pick, do not paste (ORC-18)**
    **Property: with two projects visible the Project control is a list of
    their names, the first is selected, no id field is shown, and the
    integrations of that project were requested without anyone typing an id;
    choosing the other project requests its integrations.**
    """
    page, seen = _open(browser, path="/webhooks", projects=TWO_PROJECTS)
    try:
        options = page.evaluate("() => [...document.querySelectorAll('[data-role=\"project-select\"] mj-option')].map((o) => [o.getAttribute('value'), o.textContent.trim()])")
        id_field = page.locator('[data-role="project-input"]').count()
        chosen = page.evaluate("() => document.querySelector('pyc-webhooks').projectId")
        page.locator('[data-role="project-select"]').click()
        page.get_by_role("option", name="Lab").click()
        page.wait_for_timeout(600)
        after = page.evaluate("() => document.querySelector('pyc-webhooks').projectId")
    finally:
        page.context.close()

    testbase.assert_equal(
        (options, id_field, chosen, after, seen[0], seen[-1]),
        ([[DEMO_ID, "Demo"], [LAB_ID, "Lab"]], 0, DEMO_ID, LAB_ID, DEMO_ID, LAB_ID),
    )
    return


def test_a_project_named_in_the_address_is_the_one_selected(browser: Browser):
    """
    **Feature: pick, do not paste (ORC-18)**
    **Property: ``/webhooks?project_id=<id>`` selects that project.**
    """
    page, seen = _open(browser, path="/webhooks?project_id=" + LAB_ID, projects=TWO_PROJECTS)
    try:
        chosen = page.evaluate("() => document.querySelector('pyc-webhooks').projectId")
    finally:
        page.context.close()

    testbase.assert_equal((chosen, seen[-1]), (LAB_ID, LAB_ID))
    return


def test_without_a_project_list_the_id_field_and_its_prompt_remain(browser: Browser):
    """
    **Feature: pick, do not paste (ORC-18)**
    **Property: when the projects cannot be listed (none returned) the page
    falls back to the id field and says "Enter a project id to view
    integrations."; with a project list it never says so.**
    """
    page, _seen = _open(browser, path="/webhooks", projects={"items": [], "meta": {"total": 0}})
    try:
        field = page.locator('[data-role="project-input"]').count()
        prompt = " ".join(page.locator('pyc-webhooks').inner_text().split())
    finally:
        page.context.close()
    listed, _seen2 = _open(browser, path="/webhooks", projects=TWO_PROJECTS)
    try:
        listed_text = " ".join(listed.locator('pyc-webhooks').inner_text().split())
    finally:
        listed.context.close()

    testbase.assert_equal(
        (field, "Enter a project id to view integrations." in prompt, "Enter a project id" in listed_text),
        (1, True, False),
    )
    return
