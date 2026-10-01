"""
.. module:: test_p32zzzzzzzzzzzz_resource_edit_details_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A resource's name, description and tags can be changed from its page (ORC-26).

.. moduleauthor:: Code Craft AI LLC

``PATCH /api/v1/resources/{id}`` could change a resource's name, description and tags, but the page had no way to
send it: a mistyped name stayed until the resource was retired and registered again. The resource page now has
**Edit details** (for people who may write resources, not on a retired resource): a form filled in with the
current values; Save changes sends only what changed; the page then shows the new values and the page title follows
the name. The page is opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

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

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
RESOURCE_ID: str = "7e7e7e7e-0000-4000-8000-000000000001"


def _resource(*, state: str = "available", name: str = "Rack 7 swtich", description: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "resource_id": RESOURCE_ID, "project_id": PROJECT_ID, "kind": "network_switch", "display_name": name,
        "description": description, "identity_hash": "ab" * 32, "state": state, "tags": ["lab-2", "poe"] if tags is None else tags,
        "attributes": {}, "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z",
    }


def _open(browser: Browser, *, permissions: List[str], state: str = "available", patch: Optional[Dict[str, Any]] = None) -> Any:
    """
        Open the resource page. ``patch`` is what an edit gets (default: 200 with the edited resource);
        ``page.patches`` collects the PATCH bodies.
    """
    current = {"resource": _resource(state=state)}
    patches: List[Any] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-resources-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/me/permissions": {"permissions": permissions},
            "/api/v1/resources/{}/health".format(RESOURCE_ID): {"resource_id": RESOURCE_ID, "status": "healthy"},
            "/api/v1/resources/{}/usage-history".format(RESOURCE_ID): {"items": [], "meta": {"total": 0}},
        },
    )

    def one(route: Any) -> None:
        method = route.request.method
        if method == "PATCH":
            body = json.loads(route.request.post_data or "{}")
            patches.append(body)
            answer = patch or {"status": 200}
            if answer["status"] == 200:
                current["resource"].update(body if "tags" in body or "description" in body or "display_name" in body else {})
                payload = current["resource"]
            else:
                payload = answer["body"]
            route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(payload))
            return
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps(current["resource"]))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/resources/[^/?]+$"), one)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/resource-pools/resources/" + RESOURCE_ID)
    page.wait_for_selector('[data-role="resource-id"]')
    page.wait_for_timeout(800)
    page.patches = patches
    return page


def test_edit_fills_the_form_sends_only_what_changed_and_shows_the_new_values(browser: Browser):
    """
    **Feature: resource edit details (ORC-26)**
    **Property: Edit details opens a form holding the name, description and tags (comma separated); changing the
    name and adding a description and a tag sends one PATCH with exactly those three fields (tags in order, repeats
    and blanks dropped); the page then shows the new name, the description and the tags, says it was saved, closes
    the form, and the page title follows the name.**
    """
    page = _open(browser, permissions=["system:resources.write"])
    try:
        page.locator('[data-role="edit-resource"]').click()
        page.wait_for_selector('[data-role="edit-resource-form"]')
        page.wait_for_timeout(300)
        filled = (
            page.locator('[data-role="edit-resource-name"] input').input_value(),
            page.locator('[data-role="edit-resource-description"] textarea').input_value(),
            page.locator('[data-role="edit-resource-tags"] input').input_value(),
        )
        page.locator('[data-role="edit-resource-name"] input').fill("Rack 7 switch")
        page.locator('[data-role="edit-resource-description"] textarea').fill("Top of rack, row 7")
        page.locator('[data-role="edit-resource-tags"] input').fill("lab-2, poe, , lab-2, uplink-10g")
        page.locator('[data-role="edit-resource-save"]').click()
        page.wait_for_function("() => document.querySelector('[data-role=\"edit-resource-form\"]') === null")
        page.wait_for_timeout(600)
        status = page.locator('[data-role="action-status"]').inner_text()
        text = " ".join(page.locator('[data-role="body"]').inner_text().split())
        title = page.title()
        patches = list(page.patches)
    finally:
        page.context.close()

    testbase.assert_equal(
        (filled, patches, status, "Rack 7 switch" in text, "Top of rack, row 7" in text, "uplink-10g" in text, "Rack 7 switch" in title),
        (
            ("Rack 7 swtich", "", "lab-2, poe"),
            [{"display_name": "Rack 7 switch", "description": "Top of rack, row 7", "tags": ["lab-2", "poe", "uplink-10g"]}],
            "Resource details saved.", True, True, True, True,
        ),
    )
    return


def test_nothing_changed_and_an_emptied_name_send_nothing(browser: Browser):
    """
    **Feature: resource edit details (ORC-26)**
    **Property: saving the form as it opened says "Nothing to change." and sends no request; emptying the name
    is refused on the page ("The display name cannot be empty.") and sends no request; Cancel closes the form.**
    """
    page = _open(browser, permissions=["system:resources.write"])
    try:
        page.locator('[data-role="edit-resource"]').click()
        page.wait_for_selector('[data-role="edit-resource-form"]')
        page.wait_for_timeout(300)
        page.locator('[data-role="edit-resource-name"] input').fill("")
        page.locator('[data-role="edit-resource-save"]').click()
        page.wait_for_timeout(300)
        emptied = (page.locator('[data-role="edit-resource-status"]').inner_text(), len(page.patches))
        page.locator('[data-role="edit-resource-name"] input').fill("Rack 7 swtich")
        page.locator('[data-role="edit-resource-save"]').click()
        page.wait_for_timeout(400)
        unchanged = (page.locator('[data-role="action-status"]').inner_text(), len(page.patches), page.locator('[data-role="edit-resource-region"]').evaluate("el => el.hidden"))
        page.locator('[data-role="edit-resource"]').click()
        page.wait_for_selector('[data-role="edit-resource-form"]')
        page.locator('[data-role="edit-resource-cancel"]').click()
        page.wait_for_timeout(200)
        cancelled = page.locator('[data-role="edit-resource-region"]').evaluate("el => el.hidden")
    finally:
        page.context.close()

    testbase.assert_equal((emptied, unchanged, cancelled), ((("The display name cannot be empty."), 0), ("Nothing to change.", 0, True), True))
    return


def test_a_refused_edit_says_why_and_keeps_the_form_open(browser: Browser):
    """
    **Feature: resource edit details (ORC-26)**
    **Property: a 409 (the resource was retired meanwhile) is said in words next to the form and the form stays
    open with the person's values.**
    """
    page = _open(browser, permissions=["system:resources.write"], patch={"status": 409, "body": {"detail": "Resource is retired."}})
    try:
        page.locator('[data-role="edit-resource"]').click()
        page.wait_for_selector('[data-role="edit-resource-form"]')
        page.wait_for_timeout(300)
        page.locator('[data-role="edit-resource-name"] input').fill("Rack 7 switch")
        page.locator('[data-role="edit-resource-save"]').click()
        page.wait_for_timeout(600)
        message = page.locator('[data-role="edit-resource-status"]').inner_text()
        kept = page.locator('[data-role="edit-resource-name"] input').input_value()
        open_still = page.locator('[data-role="edit-resource-region"]').evaluate("el => el.hidden") is False
    finally:
        page.context.close()

    testbase.assert_equal((message, kept, open_still), ("This resource is retired and can no longer be edited.", "Rack 7 switch", True))
    return


def test_no_edit_button_without_write_permission_or_on_a_retired_resource(browser: Browser):
    """
    **Feature: resource edit details (ORC-26)**
    **Property: Edit details is offered only to people who may write resources, and not on a retired resource
    (retirement is terminal, the API refuses the edit).**
    """
    reader = _open(browser, permissions=["system:resources.read"])
    try:
        without_permission = reader.locator('[data-role="edit-resource"]').count()
    finally:
        reader.context.close()
    retired = _open(browser, permissions=["system:resources.write"], state="retired")
    try:
        on_retired = retired.locator('[data-role="edit-resource"]').count()
    finally:
        retired.context.close()

    testbase.assert_equal((without_permission, on_retired), (0, 0))
    return
