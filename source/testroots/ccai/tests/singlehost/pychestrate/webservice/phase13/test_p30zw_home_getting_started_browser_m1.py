"""
.. module:: test_p30zw_home_getting_started_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The home page leads with a getting-started checklist
               driven by what exists (LD-10).

.. moduleauthor:: Code Craft AI LLC

After setup a new administrator landed on a site map of 37 links with
nothing saying what to do first. The home page now shows a three-step
checklist (create a project, enroll a pod, run something) whose done
marks come from the projects, clients and runs lists, then the newest
runs once there are some. The list of every section stays one click
away, and opens by itself when the numbers cannot be read. A step's
links appear only for a person who can reach the page.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    NAV_ENTRIES,
    build_navigation_manifest,
)
from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    all_navigation_permissions,
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-00000000000d"
CLIENT_ID: str = "0f6c2c1e-7777-4000-8000-00000000000e"


def _stubs(*, projects: int, clients: int, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
        API answers shaped like the service's: the projects and runs
        lists are ``{items, meta}``; the clients list is a bare array.
    """
    rtnval = {
        "/api/v1/projects": {
            "items": [{"project_id": PROJECT_ID}] * min(projects, 1),
            "meta": {"page": 1, "per_page": 1, "total": projects},
        },
        "/api/v1/clients": [{"client_id": CLIENT_ID}] * min(clients, 1),
        "/api/v1/runs": {"items": runs, "meta": {"page": 1, "per_page": 5, "total": len(runs)}},
    }
    return rtnval


def _run(index: int, state: str) -> Dict[str, Any]:
    rtnval = {
        "run_id": "0f6c2c1e-8888-4000-8000-0000000000{:02d}".format(index),
        "state": state,
        "created_at": "2026-09-26T19:12:28+00:00",
        "completed_at": "2026-09-26T19:14:41+00:00",
    }
    return rtnval


def _open_home(browser: Browser, **options: Any) -> Any:
    page = open_shell_page(browser, path="/", **DESKTOP, **options)
    page.wait_for_selector("[data-home-ready=true]")
    return page


#: JS: what the checklist shows, step by step.
STEPS_JS: str = r"""
() => Array.from(document.querySelectorAll('[data-role=getting-started] [data-step]')).map((li) => ({
  step: li.getAttribute('data-step'),
  state: li.getAttribute('data-state'),
  links: Array.from(li.querySelectorAll('a')).map((a) => a.getAttribute('href')),
}))
"""


def test_an_empty_deployment_shows_three_steps_to_do(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: with no project, pod or run, the checklist has three
    steps, all to do, and the first links to creating a project.**
    """
    page = _open_home(browser, api_stubs=_stubs(projects=0, clients=0, runs=[]))
    try:
        steps = page.evaluate(STEPS_JS)
        testbase.assert_equal(
            ([(s["step"], s["state"]) for s in steps], steps[0]["links"], steps[1]["links"]),
            (
                [("project", "todo"), ("pod", "todo"), ("run", "todo")],
                ["/projects/create"],
                ["/admin/enrollment-tokens"],
            ),
        )
    finally:
        page.context.close()
    return


def test_a_step_is_done_when_its_thing_exists(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: a project and an enrolled pod (the clients list is a
    bare array) mark the first two steps done and leave the run step
    to do; a done step offers no links.**
    """
    page = _open_home(browser, api_stubs=_stubs(projects=2, clients=1, runs=[]))
    try:
        steps = page.evaluate(STEPS_JS)
        testbase.assert_equal(
            [(s["step"], s["state"], s["links"]) for s in steps],
            [
                ("project", "done", []),
                ("pod", "done", []),
                ("run", "todo", ["/test-catalog", "/builds", "/runs"]),
            ],
        )
    finally:
        page.context.close()
    return


def test_a_set_up_deployment_shows_recent_runs_instead_of_the_checklist(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: once there is a project, a pod and a run, the checklist
    is gone and the newest runs are listed, each linking to its page and
    toned by its state.**
    """
    runs = [_run(1, "completed"), _run(2, "failed"), _run(3, "cancelled")]
    page = _open_home(browser, api_stubs=_stubs(projects=1, clients=1, runs=runs))
    try:
        found = page.evaluate(
            "() => ({checklist: document.querySelectorAll('[data-role=getting-started]').length,"
            " links: Array.from(document.querySelectorAll('[data-role=recent-runs] .pyc-site-shell__recent-run a')).map((a) => a.getAttribute('href')),"
            " tones: Array.from(document.querySelectorAll('[data-role=recent-runs] mj-chip')).map((c) => c.getAttribute('data-tone'))})"
        )
        testbase.assert_equal(
            (found["checklist"], found["links"], found["tones"]),
            (0, [
                "/runs/0f6c2c1e-8888-4000-8000-000000000001",
                "/runs/0f6c2c1e-8888-4000-8000-000000000002",
                "/runs/0f6c2c1e-8888-4000-8000-000000000003",
            ], ["ok", "error", "warn"]),
        )
    finally:
        page.context.close()
    return


def test_every_section_is_still_one_click_away(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: the full list of sections is inside "All sections", which
    is closed while the checklist shows, and holds the same links the
    sidebar does.**
    """
    page = _open_home(browser, api_stubs=_stubs(projects=0, clients=0, runs=[]))
    try:
        found = page.evaluate(
            "() => { const d = document.querySelector('[data-role=all-sections]');"
            " return {open: d.open, links: d.querySelectorAll('a.pyc-site-shell__nav-grid-link').length}; }"
        )
        testbase.assert_equal((found["open"], found["links"] > 20), (False, True), str(found))
    finally:
        page.context.close()
    return


def test_unreadable_numbers_open_the_section_list_instead(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: when none of the lists can be read, there is no
    checklist that would wrongly say nothing is set up; the section list
    opens by itself.**
    """
    page = _open_home(
        browser,
        api_stubs=_stubs(projects=0, clients=0, runs=[]),
        blocked_paths=["/api/v1/projects", "/api/v1/clients", "/api/v1/runs"],
    )
    try:
        found = page.evaluate(
            "() => ({checklist: document.querySelectorAll('[data-role=getting-started]').length,"
            " open: document.querySelector('[data-role=all-sections]').open})"
        )
        testbase.assert_equal((found["checklist"], found["open"]), (0, True))
    finally:
        page.context.close()
    return


def _stubs_without_enrollment_access() -> Dict[str, Any]:
    """
        Navigation and permissions for a person who cannot open the
        enrollment page (it needs ``system:resources.manage``).
    """
    blocked: Optional[List[str]] = None
    for entry in NAV_ENTRIES:
        if entry.route == "/admin/enrollment-tokens":
            blocked = list(entry.required_permissions)
    testbase.assert_true(blocked is not None, "enrollment entry not found")
    held = [key for key in all_navigation_permissions() if key not in blocked]
    rtnval = _stubs(projects=0, clients=0, runs=[])
    rtnval["/api/v1/me/permissions"] = {"permissions": held}
    rtnval["/api/v1/me/navigation"] = build_navigation_manifest(held_permissions=held)
    return rtnval


def test_a_person_who_cannot_enroll_a_pod_is_told_to_ask(browser: Browser):
    """
    **Feature: home page (LD-10)**
    **Property: without access to the enrollment page the pod step has
    no link to it and says to ask an administrator.**
    """
    page = _open_home(browser, api_stubs=_stubs_without_enrollment_access())
    try:
        found = page.evaluate(
            "() => { const li = document.querySelector('[data-step=pod]');"
            " return {links: Array.from(li.querySelectorAll('a')).map((a) => a.getAttribute('href')),"
            " text: li.textContent}; }"
        )
        testbase.assert_equal(
            (found["links"], "Ask an administrator" in found["text"]), ([], True), str(found),
        )
    finally:
        page.context.close()
    return
