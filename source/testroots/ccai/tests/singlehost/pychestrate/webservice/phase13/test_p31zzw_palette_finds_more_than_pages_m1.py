"""
.. module:: test_p31zzw_palette_finds_more_than_pages_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The command palette finds projects, records by id and actions (XC-17).

.. moduleauthor:: Code Craft AI LLC

The palette matched only navigation entries: "checkout", a project's name,
"create", "sign out" and "theme" all answered "No results". It now also finds
a project by name, a user by login or display name (for someone who may list
users), opens a run or build from a pasted id, and runs a few common actions
(create a project, register a device, switch theme, sign out).
A source that matched nothing shows no heading while another has results, and
one line ("No results.") when nothing matched anywhere. The shell is opened in
a browser against stubbed API answers and the palette is used from the
keyboard.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

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

PROJECTS = {
    "items": [
        {"project_id": "0f6c2c1e-6666-4000-8000-000000000001", "display_name": "Demo", "slug": "demo"},
        {"project_id": "0f6c2c1e-6666-4000-8000-000000000002", "display_name": "Orchestrate", "slug": "orchestrate"},
    ],
    "meta": {"total": 2},
}

RUN_ID: str = "aaaaaaaa-1111-4000-8000-000000000001"

USER_ID: str = "bbbbbbbb-2222-4000-8000-000000000001"


def _users_answer(query: Dict[str, Any]) -> Dict[str, Any]:
    """The picker list the server gives: the users whose login or display name contains ``q``."""
    people = [
        {"user_id": USER_ID, "login_name": "ada", "display_name": "Ada Lovelace", "status": "ACTIVE"},
        {"user_id": "bbbbbbbb-2222-4000-8000-000000000002", "login_name": "adam", "display_name": "Adam Old", "status": "DEACTIVATED"},
    ]
    wanted = str(query.get("q", [""])[0] if isinstance(query.get("q"), list) else query.get("q", "")).lower()
    items = [person for person in people if wanted in person["login_name"] or wanted in person["display_name"].lower()]
    return {"items": items, "meta": {"page": 1, "per_page": 6, "total": len(items)}}


def _search(page: Any, text: str) -> Dict[str, Any]:
    """Type ``text`` into the open palette; return its groups (heading -> option labels) and status line."""
    page.locator(".pyc-site-shell__palette-input").fill("")
    page.locator(".pyc-site-shell__palette-input").fill(text)
    page.wait_for_timeout(900)
    return page.evaluate(
        """() => {
            const groups = {};
            document.querySelectorAll('.pyc-site-shell__palette-group').forEach((group) => {
                const heading = group.querySelector('.pyc-site-shell__palette-group-label').textContent.trim();
                groups[heading] = [...group.querySelectorAll('.pyc-site-shell__palette-option-label')].map((o) => o.textContent.trim());
            });
            const status = document.querySelector('.pyc-site-shell__palette-status, [role=status]');
            return {groups, all_headings: [...document.querySelectorAll('.pyc-site-shell__palette-group-label')].map((h) => h.textContent.trim())};
        }"""
    )


def _open(browser: Browser) -> Any:
    page = open_shell_page(browser, path="/", api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP)
    page.keyboard.press("Control+k")
    page.wait_for_selector(".pyc-site-shell__palette-input")
    return page


def test_a_project_is_found_by_name_and_opened(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: typing part of a project's name lists it under "Projects"
    (with its slug), other sources that matched nothing show no heading, and
    Enter opens the project's page.**
    """
    page = _open(browser)
    try:
        found = _search(page, "demo")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        path = urllib.parse.urlparse(page.url).path
    finally:
        page.context.close()

    testbase.assert_equal(
        (found["groups"].get("Projects"), found["all_headings"], path),
        (["Demo"], ["Projects"], "/projects/demo"),
    )
    return


def test_actions_are_found_by_what_a_person_would_type(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: "checkout" finds Register a device, "create" finds the actions that
    create something, and "theme" finds Switch theme; choosing Switch theme flips the
    theme.**
    """
    page = _open(browser)
    try:
        checkout = _search(page, "checkout")["groups"].get("Actions")
        create = _search(page, "create")["groups"].get("Actions")
        theme = _search(page, "theme")["groups"].get("Actions")
        before = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        after = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
    finally:
        page.context.close()

    testbase.assert_equal(
        (checkout, sorted(create or []), theme, before != after),
        (["Register a device"], ["Create a project", "Create an API token", "Define a pipeline"], ["Switch theme"], True),
    )
    return


def test_a_pasted_run_or_build_id_opens_it(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: pasting a full id offers "Run <short>" and "Build <short>"
    under "Open by id"; choosing the first opens ``/runs/<id>``. A partial id
    offers nothing.**
    """
    page = _open(browser)
    try:
        partial = _search(page, RUN_ID[:8])["groups"].get("Open by id")
        found = _search(page, RUN_ID)["groups"].get("Open by id")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        path = urllib.parse.urlparse(page.url).path
    finally:
        page.context.close()

    testbase.assert_equal((partial, found, path), (None, ["Run aaaaaaaa", "Build aaaaaaaa"], "/runs/" + RUN_ID))
    return


def test_a_query_nothing_matches_says_so_once(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: when nothing matches anywhere the palette shows no group
    headings, only "No results.".**
    """
    page = _open(browser)
    try:
        found = _search(page, "zzzzqqqq")
        status = page.evaluate("() => document.querySelector('.pyc-site-shell__palette-dialog, dialog')?.textContent || document.body.textContent")
    finally:
        page.context.close()

    testbase.assert_equal((found["all_headings"], "No results." in status), ([], True))
    return


def test_a_user_is_found_by_login_or_name_and_opened(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: for someone who may list users, typing part of a login or display
    name lists the matching users under "Users" (a deactivated one is marked in its
    description), and Enter opens the user's admin page.**
    """
    page = open_shell_page(browser, path="/", api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/identity/users": _users_answer}, **DESKTOP)
    page.keyboard.press("Control+k")
    page.wait_for_selector(".pyc-site-shell__palette-input")
    try:
        # "adam" is also part of no page name; a deactivated user is marked in the description
        deactivated = _search(page, "adam")["groups"].get("Users")
        descriptions = page.evaluate("() => [...document.querySelectorAll('.pyc-site-shell__palette-option-description')].map((o) => o.textContent.trim())")
        # a display name no page is called: the user is the only match, so Enter opens it
        found = _search(page, "lovelace")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        path = urllib.parse.urlparse(page.url).path
    finally:
        page.context.close()

    testbase.assert_equal(
        (deactivated, [text for text in descriptions if text.startswith("User")], found["groups"].get("Users"), path),
        (["Adam Old"], ["User · adam · deactivated"], ["Ada Lovelace"], "/admin/users/" + USER_ID),
    )
    return


def test_users_are_not_searched_for_someone_who_may_not_list_them(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: when the viewer's permissions do not include system:users.read the
    palette offers no Users source and never asks the server for users.**
    """
    stubs = {
        "/api/v1/projects": PROJECTS,
        "/api/v1/identity/users": _users_answer,
        "/api/v1/me/permissions": {"permissions": ["system:projects.access"]},
    }
    page = open_shell_page(browser, path="/", api_stubs=stubs, **DESKTOP)
    asked: List[str] = []
    page.on("request", lambda request: asked.append(request.url) if "/api/v1/identity/users" in request.url else None)
    page.keyboard.press("Control+k")
    page.wait_for_selector(".pyc-site-shell__palette-input")
    try:
        found = _search(page, "ada")
    finally:
        page.context.close()

    testbase.assert_equal((found["groups"].get("Users"), asked), (None, []))
    return


def test_a_failing_user_search_shows_no_users_and_no_error(browser: Browser):
    """
    **Feature: a palette that finds things (XC-17)**
    **Property: when the users request fails (here: the server has no such answer),
    the palette shows no Users heading and no "unavailable" message, and the other
    sources still answer.**
    """
    page = open_shell_page(browser, path="/", api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP)
    page.keyboard.press("Control+k")
    page.wait_for_selector(".pyc-site-shell__palette-input")
    try:
        found = _search(page, "demo")
        text = page.locator(".pyc-site-shell__palette-dialog, [role=dialog]").first.inner_text()
    finally:
        page.context.close()

    testbase.assert_equal((found["groups"].get("Projects"), found["groups"].get("Users"), "unavailable" in text.lower()), (["Demo"], None, False))
    return
