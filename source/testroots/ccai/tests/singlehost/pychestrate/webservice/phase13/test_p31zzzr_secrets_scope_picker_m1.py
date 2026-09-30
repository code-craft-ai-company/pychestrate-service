"""
.. module:: test_p31zzzr_secrets_scope_picker_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A secret's project or user is chosen by name, not typed as an id (ADM-29).

.. moduleauthor:: Code Craft AI LLC

The Project and User tabs of the Secrets page asked for a "Scope reference": an id
to type from memory, with the same placeholder ("project id or user id") on both
tabs. Each tab now lists the owners by name (projects from the projects list, users
from the new user list) and starts on the first, so the secrets of a real owner are
shown at once; the table names the owner and keeps the id on hover; when a list
cannot be read in full the typed field returns, labelled for the tab, with the
reason. The real page is opened in a browser against stubbed API answers.
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

ALPHA: str = "0f6c2c1e-dddd-4000-8000-00000000000a"
BETA: str = "0f6c2c1e-dddd-4000-8000-00000000000b"
ADA: str = "0f6c2c1e-dddd-4000-8000-0000000000a1"
GRACE: str = "0f6c2c1e-dddd-4000-8000-0000000000a2"

PROJECTS = {"items": [
    {"project_id": ALPHA, "display_name": "Alpha", "slug": "alpha"}, {"project_id": BETA, "display_name": "Beta", "slug": "beta"},
], "meta": {"total": 2}}
USERS = {"items": [
    {"user_id": ADA, "login_name": "ada", "display_name": "Ada Lovelace", "status": "active"},
    {"user_id": GRACE, "login_name": "grace", "display_name": "grace", "status": "active"},
], "meta": {"page": 1, "per_page": 200, "total": 2}}


def _secret(name: str, kind: str, ref: Optional[str]) -> Dict[str, Any]:
    return {
        "secret_ref": name, "backend_name": "local", "scope_kind": kind, "scope_ref": ref, "current_version_id": "v1",
        "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00",
    }


def _open(browser: Browser, *, users: Any = USERS, users_status: int = 200) -> Any:
    """Open /secrets; the list requests' (scope_kind, scope_ref) are collected on ``page.listed`` and POST bodies on ``page.posted``."""
    listed: List[Any] = []
    posted: List[Dict[str, Any]] = []

    def secrets(query: Dict[str, str]) -> Any:
        listed.append((query.get("scope_kind"), query.get("scope_ref")))
        if query.get("scope_ref") == ALPHA:
            return [_secret("alpha/db-password", "PROJECT", ALPHA)]
        if query.get("scope_ref") == ADA:
            return [_secret("ada/token", "USER", ADA)]
        return []

    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-secrets-bundle"],
        api_stubs={"/api/v1/secrets": secrets, "/api/v1/projects": PROJECTS, "/api/v1/identity/users": users},
    )
    if users_status != 200:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/identity/users(\?.*)?$"),
            lambda route: route.fulfill(status=users_status, headers={"Content-Type": "application/json"}, body=b"{}"),
        )

    def create(route: Any) -> None:
        request = route.request
        if request.method == "POST":
            posted.append(json.loads(request.post_data))
            route.fulfill(status=201, headers={"Content-Type": "application/json"}, body=json.dumps(_secret("new", "PROJECT", ALPHA)).encode("utf-8"))
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/secrets(\?.*)?$"), create)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.listed = listed
    page.posted = posted
    page.goto(FAKE_ORIGIN + "/secrets")
    page.wait_for_selector('[role="tab"]')
    page.wait_for_timeout(1000)
    return page


def _tab(page: Any, name: str) -> None:
    page.get_by_role("tab", name=name).click()
    page.wait_for_timeout(900)


def _state(page: Any) -> Dict[str, Any]:
    return page.evaluate(
        """() => {
            const visible = (el) => !!el && !el.hidden && el.getBoundingClientRect().width > 0;
            const select = document.querySelector('[data-role="scope-ref-select"]');
            const input = document.querySelector('[data-role="scope-ref-input"]');
            const note = document.querySelector('[data-role="scope-ref-note"]');
            return {
                select_visible: visible(select), input_visible: visible(input),
                select_label: select && select.closest('label') ? select.closest('label').querySelector('[data-role="scope-ref-picker-label"]').textContent : null,
                options: select ? [...select.querySelectorAll('mj-option')].map((o) => o.textContent.trim()) : [],
                value: select ? select.value : null,
                input_label: input ? input.getAttribute('label') : null, input_placeholder: input ? input.getAttribute('placeholder') : null,
                note: note && !note.hidden ? note.textContent.trim() : null,
            };
        }"""
    )


def test_the_project_tab_lists_projects_by_name_and_shows_the_first_ones_secrets(browser: Browser):
    """
    **Feature: secrets scope picker (ADM-29)**
    **Property: on the Project tab the typed field is gone; a labelled list ("Project"
    names the select) offers "Alpha" and "Beta", Alpha is chosen, and the secrets of Alpha (not a blank query) are
    listed; the table names the owner "Alpha" with the id on hover; choosing Beta
    asks for Beta's secrets.**
    """
    page = _open(browser)
    try:
        _tab(page, "Project")
        state = _state(page)
        owner = page.locator(".pyc-secrets__scope-ref-text").first
        shown = (owner.inner_text(), owner.get_attribute("title"))
        page.evaluate(
            "(id) => { const s = document.querySelector('[data-role=\"scope-ref-select\"]'); s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); }",
            BETA,
        )
        page.wait_for_timeout(700)
        listed = list(page.listed)
    finally:
        page.context.close()

    testbase.assert_equal(
        (state["select_visible"], state["input_visible"], state["select_label"], state["options"], state["value"], shown, listed[-2:]),
        (True, False, "Project", ["Alpha", "Beta"], ALPHA, ("Alpha", ALPHA), [("PROJECT", ALPHA), ("PROJECT", BETA)]),
    )
    return


def test_the_user_tab_lists_users_by_name_and_a_new_secret_goes_to_the_chosen_owner(browser: Browser):
    """
    **Feature: secrets scope picker (ADM-29)**
    **Property: on the User tab the list reads "Ada Lovelace (ada)" and "grace" (a
    display name equal to the login is not repeated); Ada's secrets are listed; a
    secret created there is posted with Ada's id as its scope reference.**
    """
    page = _open(browser)
    try:
        _tab(page, "User")
        state = _state(page)
        page.locator('[data-role="create-name"] input').fill("ada/new")
        page.locator('mj-text-field[type="password"] input, [data-role="create-value"] input').first.fill("s3cret")
        page.get_by_role("button", name="Create Secret").click()
        page.wait_for_timeout(900)
        posted = list(page.posted)
    finally:
        page.context.close()

    testbase.assert_equal(
        (state["select_label"], state["options"], state["value"], [(item.get("scope_kind"), item.get("scope_ref")) for item in posted]),
        ("User", ["Ada Lovelace (ada)", "grace"], ADA, [("USER", ADA)]),
    )
    return


def test_a_list_that_cannot_be_read_or_is_incomplete_brings_the_typed_field_back_with_the_reason(browser: Browser):
    """
    **Feature: secrets scope picker (ADM-29)**
    **Property: when the user list is refused (403) or holds fewer users than exist,
    the User tab shows the typed field labelled "User id" with a note saying why;
    typing an id lists that owner's secrets. The Project tab still has its list.**
    """
    results: Dict[str, Any] = {}
    for name, options in (
        ("refused", dict(users={}, users_status=403)),
        ("incomplete", dict(users={"items": USERS["items"], "meta": {"page": 1, "per_page": 2, "total": 500}})),
    ):
        page = _open(browser, **options)
        try:
            _tab(page, "User")
            state = _state(page)
            page.locator('[data-role="scope-ref-input"] input').fill(ADA)
            page.locator('[data-role="scope-ref-input"] input').dispatch_event("change")
            page.wait_for_timeout(800)
            results[name] = (state["select_visible"], state["input_visible"], state["input_label"], state["note"] is not None and "type the id" in state["note"], ("USER", ADA) in page.listed)
        finally:
            page.context.close()

    testbase.assert_equal(results, {"refused": (False, True, "User id", True, True), "incomplete": (False, True, "User id", True, True)})
    return


def test_the_org_tab_has_no_scope_field_and_a_tab_switch_never_asks_with_a_blank_owner(browser: Browser):
    """
    **Feature: secrets scope picker (ADM-29)**
    **Property: the Org tab shows no scope field; moving to the Project tab never
    lists secrets for a project scope with no owner (the picker chooses one first).**
    """
    page = _open(browser)
    try:
        org = _state(page)
        _tab(page, "Project")
        blank = [item for item in page.listed if item[0] == "PROJECT" and not item[1]]
    finally:
        page.context.close()

    testbase.assert_equal((org["select_visible"], org["input_visible"], blank), (False, False, []))
    return
