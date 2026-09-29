"""
.. module:: test_p31zzo_register_device_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A device is registered from the Resource pools page, and added to a pool by name (RES-04).

.. moduleauthor:: Code Craft AI LLC

Nothing could register a resource, so no pool could have a member, and the
pool page's only way to add one was to paste a resource id. The Resource pools
page now lists the project's resources and registers a device (a name, the
hostname that identifies it, optional details and tags); a pool's page adds a
member from a list of the project's resources by name. The pages are opened in
a browser against stubbed API answers, the forms are filled the way a person
does, and the requests they send are captured.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    all_navigation_permissions,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
POOL_ID: str = "5a1d1a3e-7777-4000-8000-000000000002"
PHONE_ID: str = "aaaaaaaa-0000-4000-8000-000000000001"
TABLET_ID: str = "aaaaaaaa-0000-4000-8000-000000000002"
OLD_ID: str = "aaaaaaaa-0000-4000-8000-000000000003"
SWITCH_ID: str = "aaaaaaaa-0000-4000-8000-000000000004"

PERMISSIONS: List[str] = all_navigation_permissions() + ["system:resource_pools.write", "system:resources.write"]


def _resource(resource_id: str, name: str, state: str = "available") -> Dict[str, Any]:
    return {
        "resource_id": resource_id, "project_id": PROJECT_ID, "kind": "device", "display_name": name,
        "description": "", "identity_hash": "h", "state": state, "tags": ["lab"], "attributes": {"hostname": name.lower()},
        "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00",
    }


class _Site:
    """A browser context whose API answers are stubbed and whose POSTs are captured."""

    def __init__(self, browser: Browser, *, path: str, resources: List[Dict[str, Any]], members: Optional[List[Dict[str, Any]]] = None,
                 answer_post: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                 permissions: Optional[List[str]] = None) -> None:
        self.resources = list(resources)
        self.members = list(members or [])
        self.posts: List[Dict[str, Any]] = []
        self._answer_post = answer_post
        stubs = {
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "total": 1},
            "/api/v1/resource-pools": {"items": [], "meta": {"total": 0, "page": 1, "per_page": 50}},
            "/api/v1/me/permissions": {"permissions": PERMISSIONS if permissions is None else permissions},
            "/api/v1/resource-pools/" + POOL_ID: {
                "pool_id": POOL_ID, "project_id": PROJECT_ID, "name": "phones", "description": "", "capability_tags": [],
                "member_count": len(self.members), "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00",
            },
            "/api/v1/resource-pools/" + POOL_ID + "/resources": lambda query: {"items": self.members, "meta": {"total": len(self.members)}},
            "/api/v1/resource-pools/" + POOL_ID + "/reservations": {"items": [], "meta": {"total": 0}},
        }
        self.context = browser.new_context(**DESKTOP)
        bundle_names = ["pyc-site-shell", "pyc-resources-bundle"]
        install_site_routes(self.context, bundle_names=bundle_names, api_stubs=stubs)
        # A glob without ``**`` does not match a URL that has a query string.
        self.context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/resources(\?.*)?$"), self._resources_api)
        self.context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/resource-pools/" + POOL_ID + r"/resources(\?.*)?$"), self._members_api)
        self.page = self.context.new_page()
        self.page.set_default_timeout(READY_TIMEOUT_MS)
        self.page.goto(FAKE_ORIGIN + path)
        self.page.wait_for_function(
            "() => { const shell = document.querySelector('pyc-site-shell'); return shell !== null && shell.isReady === true; }"
        )

    def _resources_api(self, route: Any) -> None:
        request = route.request
        if request.method == "POST":
            body = json.loads(request.post_data)
            self.posts.append(body)
            answer = self._answer_post(body) if self._answer_post is not None else {"status": 201, "body": _resource("bbbbbbbb-0000-4000-8000-000000000001", body["display_name"])}
            if answer["status"] == 201:
                self.resources.append(answer["body"])
            route.fulfill(status=answer["status"], headers={"Content-Type": "application/json"}, body=json.dumps(answer["body"]).encode("utf-8"))
            return
        route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"items": self.resources, "meta": {"page": 1, "per_page": 500, "total": len(self.resources), "next_cursor": None}}).encode("utf-8"),
        )

    def _members_api(self, route: Any) -> None:
        request = route.request
        if request.method == "POST":
            body = json.loads(request.post_data)
            self.posts.append(body)
            route.fulfill(status=201, headers={"Content-Type": "application/json"}, body=json.dumps({
                "membership_id": "m-1", "pool_id": POOL_ID, "resource_id": body["resource_id"], "added_at": "2026-09-29T10:05:00+00:00",
                "resource_name": "x", "resource_kind": "device", "resource_state": "available", "resource_health": None,
            }).encode("utf-8"))
            return
        route.fallback()

    def close(self) -> None:
        self.context.close()


def _fill(page: Any, name: str, value: str) -> None:
    # The Create pool form has a "Name" field too: scope to the register form.
    page.locator('[data-role="register-form"]').get_by_role("textbox", name=name, exact=True).fill(value)


def test_the_resources_page_lists_the_projects_resources_and_registers_a_device(browser: Browser):
    """
    **Feature: register a device (RES-04)**
    **Property: the Resource pools page shows the project's resources in a
    table; the "Register a device" form, filled in by a person, sends the
    device kind, the name, the hostname and the optional details as attributes
    and the tags as a list; the table then shows the new device and the form
    says it was registered.**
    """
    site = _Site(browser, path="/resource-pools?project_id=" + PROJECT_ID, resources=[_resource(PHONE_ID, "Phone-1")])
    try:
        page = site.page
        page.wait_for_selector('[data-role="inventory-list"] mj-data-table')
        page.locator('[data-role="register-section"] summary').click()
        _fill(page, "Name", "Bench tablet")
        _fill(page, "Hostname", "tablet-02")
        _fill(page, "MAC address", "aa:bb:cc:dd:ee:02")
        _fill(page, "Tags", "android, lab, android")
        page.get_by_role("button", name="Register device").click()
        page.wait_for_function("() => document.querySelector('[data-role=\"register-status\"]') && !document.querySelector('[data-role=\"register-status\"]').hidden")
        status = page.locator('[data-role="register-status"]').inner_text()
        page.wait_for_function("() => (document.querySelector('[data-role=\"inventory-list\"] mj-data-table')?.rows || []).length === 2")
        after_rows = page.evaluate("() => document.querySelector('[data-role=\"inventory-list\"] mj-data-table').rows.map((row) => row.display_name)")
    finally:
        site.close()

    testbase.assert_equal(
        (
            site.posts,
            status,
            after_rows,
        ),
        (
            [{
                "project_id": PROJECT_ID, "kind": "device", "display_name": "Bench tablet",
                "attributes": {"hostname": "tablet-02", "mac_address": "aa:bb:cc:dd:ee:02"}, "tags": ["android", "lab"],
            }],
            "Registered Bench tablet.",
            ["Phone-1", "Bench tablet"],
        ),
    )
    return


def test_a_project_with_no_resources_says_how_to_add_one(browser: Browser):
    """
    **Feature: register a device (RES-04)**
    **Property: with no resources the section says so and points at the form
    below it; without the write permission it shows no form and no such
    pointer.**
    """
    writer = _Site(browser, path="/resource-pools?project_id=" + PROJECT_ID, resources=[])
    try:
        writer.page.wait_for_selector('[data-role="inventory-empty"]')
        writer_text = writer.page.locator('[data-role="inventory-empty"]').inner_text()
        writer_form = writer.page.locator('[data-role="register-section"]').count()
    finally:
        writer.close()
    reader = _Site(browser, path="/resource-pools?project_id=" + PROJECT_ID, resources=[], permissions=all_navigation_permissions())
    try:
        reader.page.wait_for_selector('[data-role="inventory-empty"]')
        reader_text = reader.page.locator('[data-role="inventory-empty"]').inner_text()
        reader_form = reader.page.locator('[data-role="register-section"]').count()
    finally:
        reader.close()

    testbase.assert_equal(
        ("Register a device below" in writer_text, writer_form, "Register" in reader_text, reader_form),
        (True, 1, False, 0),
    )
    return


def test_a_refused_registration_shows_the_servers_reason(browser: Browser):
    """
    **Feature: register a device (RES-04)**
    **Property: a 409 says the device is already registered; a 422 shows the
    server's own detail; a missing name or hostname is stopped before anything
    is sent.**
    """
    def answer(body: Dict[str, Any]) -> Dict[str, Any]:
        if body["attributes"]["hostname"] == "dup":
            return {"status": 409, "body": {"type": "/errors/conflict", "title": "Conflict", "status": 409, "detail": "A device with this identity is already registered."}}
        return {"status": 422, "body": {"type": "/errors/validation-failed", "title": "Unprocessable", "status": 422, "detail": "DeviceResourceKind: unknown attribute keys."}}

    site = _Site(browser, path="/resource-pools?project_id=" + PROJECT_ID, resources=[], answer_post=answer)
    messages: List[str] = []
    try:
        page = site.page
        page.wait_for_selector('[data-role="inventory-empty"]')
        page.locator('[data-role="register-section"] summary').click()

        def status_after_submit() -> str:
            page.get_by_role("button", name="Register device").click()
            page.wait_for_timeout(600)
            return page.locator('[data-role="register-status"]').inner_text()

        messages.append(status_after_submit())
        _fill(page, "Name", "Box")
        messages.append(status_after_submit())
        _fill(page, "Hostname", "dup")
        messages.append(status_after_submit())
        _fill(page, "Hostname", "other")
        messages.append(status_after_submit())
    finally:
        site.close()

    testbase.assert_equal(
        (messages, len(site.posts)),
        (
            [
                "A name is required.",
                "A hostname is required: it is what tells one device from another.",
                "That device is already registered (same hostname and MAC address).",
                "Not registered: DeviceResourceKind: unknown attribute keys.",
            ],
            2,
        ),
    )
    return


def test_a_pool_adds_a_member_from_a_list_of_the_projects_resources(browser: Browser):
    """
    **Feature: register a device (RES-04)**
    **Property: the pool page's Add resource control is a list of the
    project's resources by name: it leaves out a resource already in the pool
    and a retired one, and choosing one sends that resource's id.**
    """
    members = [{
        "membership_id": "m-0", "pool_id": POOL_ID, "resource_id": PHONE_ID, "added_at": "2026-09-29T10:01:00+00:00",
        "resource_name": "Phone-1", "resource_kind": "device", "resource_state": "available", "resource_health": None,
    }]
    site = _Site(
        browser, path="/resource-pools/{}?project_id={}".format(POOL_ID, PROJECT_ID),
        resources=[_resource(PHONE_ID, "Phone-1"), _resource(TABLET_ID, "Tablet-2"), _resource(OLD_ID, "Old-3", state="retired"), _resource(SWITCH_ID, "Switch-4")],
        members=members,
    )
    try:
        page = site.page
        page.wait_for_selector('[data-role="add-resource-select"]')
        options = page.evaluate("() => [...document.querySelectorAll('[data-role=\"add-resource-select\"] mj-option')].map((o) => [o.getAttribute('value'), o.textContent.trim()])")
        has_uuid_field = page.locator('[data-role="add-resource-id"]').count()
        page.locator('[data-role="add-resource-select"]').click()
        page.get_by_role("option", name="Tablet-2 · device").click()
        page.get_by_role("button", name="Add Resource").click()
        page.wait_for_timeout(600)
    finally:
        site.close()

    testbase.assert_equal(
        (options, has_uuid_field, site.posts),
        ([[TABLET_ID, "Tablet-2 · device"], [SWITCH_ID, "Switch-4 · device"]], 0, [{"resource_id": TABLET_ID}]),
    )
    return


def test_a_pool_with_every_resource_already_in_it_says_so_and_points_to_registering_one(browser: Browser):
    """
    **Feature: register a device (RES-04)**
    **Property: when nothing is left to add, the pool page says so and links
    to the Resource pools page (where a device is registered), and shows no
    form.**
    """
    members = [{
        "membership_id": "m-0", "pool_id": POOL_ID, "resource_id": PHONE_ID, "added_at": "2026-09-29T10:01:00+00:00",
        "resource_name": "Phone-1", "resource_kind": "device", "resource_state": "available", "resource_health": None,
    }]
    site = _Site(
        browser, path="/resource-pools/{}?project_id={}".format(POOL_ID, PROJECT_ID),
        resources=[_resource(PHONE_ID, "Phone-1")], members=members,
    )
    try:
        page = site.page
        page.wait_for_selector('[data-role="add-resource-none"]')
        text = page.locator('[data-role="add-resource-none"]').inner_text()
        href = page.locator('[data-role="add-resource-none"] a').get_attribute("href")
        forms = page.locator('[data-role="add-resource-form"]').count()
    finally:
        site.close()

    testbase.assert_equal(
        ("already in this pool" in text, href, forms),
        (True, "/resource-pools?project_id=" + PROJECT_ID, 0),
    )
    return
