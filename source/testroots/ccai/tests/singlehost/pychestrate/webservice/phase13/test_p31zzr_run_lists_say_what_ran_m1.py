"""
.. module:: test_p31zzr_run_lists_say_what_ran_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Run, build and provisioning lists lead with what ran (ORC-11).

.. moduleauthor:: Code Craft AI LLC

The lists led with 8-character hashes ("Rows lead with 8-character hashes"),
so a person could not tell one run from another without opening it. A row now
leads with what ran (a run's job name, a build's runner and target, a
provisioning run's action and driver), keeps the short id after it for anyone
who must quote it, and shows how long it took. The API already sends the job
name, type, source and timings; nothing new is asked of the server. The pages
are opened in a browser against stubbed API answers and the rows are read.
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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1600, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"

PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}

PAGE_META = {"page": 1, "per_page": 50, "total": 3}


def _rows_of(page: Any, selector: str) -> List[Dict[str, Any]]:
    """The rows the table was given (what a person reads), by column key."""
    return page.evaluate("(sel) => document.querySelector(sel).rows", selector)


def _cells_text(page: Any, selector: str) -> List[List[str]]:
    """The visible text of each rendered row's cells."""
    return page.evaluate(
        """(sel) => {
            const table = document.querySelector(sel);
            const rows = table.shadowRoot ? [...table.shadowRoot.querySelectorAll('[part~="row"]')] : [];
            return rows.map((row) => [...row.querySelectorAll('[part~="cell"]')].map((cell) => cell.textContent.replace(/\\s+/g, ' ').trim()));
        }""",
        selector,
    )


def test_the_runs_list_leads_with_the_job_name_then_type_and_shows_the_duration(browser: Browser):
    """
    **Feature: run lists say what ran (ORC-11)**
    **Property: each run row starts with its job name (its kind when it has
    none) followed by the short id, then the type spelled out ("Test ·
    testbase", "Build · makefile"), the project, the state, the creation time
    and how long it ran ("3m 12s"; "—" when it never started).**
    """
    runs = {
        "items": [
            {"run_id": "aaaaaaaa-1111-4000-8000-000000000001", "project_id": PROJECT_ID, "job_name": "nightly-regression", "job_type": "testbase",
             "state": "completed", "created_at": "2026-09-29T10:00:00+00:00", "started_at": "2026-09-29T10:00:05+00:00", "completed_at": "2026-09-29T10:03:17+00:00"},
            {"run_id": "bbbbbbbb-2222-4000-8000-000000000002", "project_id": PROJECT_ID, "job_name": None, "job_type": "build-makefile",
             "state": "pending", "created_at": "2026-09-29T11:00:00+00:00", "started_at": None, "completed_at": None},
            {"run_id": "cccccccc-3333-4000-8000-000000000003", "project_id": PROJECT_ID, "job_name": "", "job_type": "rpa-process",
             "state": "failed", "created_at": "2026-09-29T09:00:00+00:00", "started_at": "2026-09-29T09:00:00+00:00", "completed_at": "2026-09-29T09:00:45+00:00"},
        ],
        "meta": PAGE_META,
    }
    page = open_shell_page(
        browser, path="/runs?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/runs": runs}, **DESKTOP,
    )
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(600)
        text = _cells_text(page, "mj-data-table")
        headers = page.evaluate("() => [...document.querySelector('mj-data-table').columns].map((c) => c.label)")
    finally:
        page.context.close()

    testbase.assert_equal(
        (headers, [row[:2] for row in text], [row[-1] for row in text]),
        (
            ["Job", "Type", "Project", "State", "Created", "Duration"],
            [["nightly-regression aaaaaaaa", "Test · testbase"], ["Build · makefile bbbbbbbb", "Build · makefile"], ["RPA · process cccccccc", "RPA · process"]],
            ["3m 12s", "—", "45s"],
        ),
    )
    return


def test_the_builds_list_leads_with_the_runner_and_target_and_shows_the_source(browser: Browser):
    """
    **Feature: run lists say what ran (ORC-11)**
    **Property: each build row starts with its runner kind and target followed
    by the short id, shows where its source came from ("main @ github.com/…",
    "—" when it has none) and how long it took.**
    """
    builds = {
        "items": [
            {"run_id": "dddddddd-4444-4000-8000-000000000004", "project_id": PROJECT_ID, "runner_kind": "makefile", "inputs": {"target": "docs"},
             "repro_digest_sha256": "abcdef0123456789", "state": "completed", "started_at": "2026-09-29T10:00:00+00:00", "finished_at": "2026-09-29T10:01:40+00:00",
             "source": {"kind": "git", "url": "https://github.com/acme/widgets.git", "ref": "main", "integration_id": "i-1"}},
            {"run_id": "eeeeeeee-5555-4000-8000-000000000005", "project_id": PROJECT_ID, "runner_kind": "makefile", "inputs": {},
             "repro_digest_sha256": "0123456789abcdef", "state": "pending", "started_at": None, "finished_at": None, "source": None},
        ],
        "meta": {"page": 1, "per_page": 50, "total": 2},
    }
    page = open_shell_page(
        browser, path="/builds?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-builds-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/projects/{}/builds".format(PROJECT_ID): builds}, **DESKTOP,
    )
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(600)
        text = _cells_text(page, "mj-data-table")
        headers = page.evaluate("() => [...document.querySelector('mj-data-table').columns].map((c) => c.label)")
    finally:
        page.context.close()

    testbase.assert_equal(
        (headers, [row[0] for row in text], [row[1] for row in text], [row[-1] for row in text]),
        (
            ["Build", "Source", "State", "Inputs digest", "Started", "Duration"],
            ["makefile · docs dddddddd", "makefile eeeeeeee"],
            ["main @ github.com/acme/widgets", "—"],
            ["1m 40s", "—"],
        ),
    )
    return


def test_the_provisioning_list_leads_with_the_action_and_driver(browser: Browser):
    """
    **Feature: run lists say what ran (ORC-11)**
    **Property: each provisioning row starts with its action and driver
    ("apply · terraform") followed by the short id, and shows how long it ran.**
    """
    runs = {
        "items": [
            {"run_id": "ffffffff-6666-4000-8000-000000000006", "project_id": PROJECT_ID, "environment_id": "11111111-7777-4000-8000-000000000007",
             "driver_name": "terraform", "action": "apply", "state": "completed",
             "started_at": "2026-09-29T08:00:00+00:00", "finished_at": "2026-09-29T08:12:03+00:00"},
        ],
        "meta": {"page": 1, "per_page": 50, "total": 1},
    }
    page = open_shell_page(
        browser, path="/provisioning-runs?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-infra-bundle"],
        api_stubs={"/api/v1/projects": PROJECTS, "/api/v1/projects/{}/provisioning-runs".format(PROJECT_ID): runs}, **DESKTOP,
    )
    try:
        page.wait_for_selector("mj-data-table")
        page.wait_for_timeout(600)
        text = _cells_text(page, "mj-data-table")
        headers = page.evaluate("() => [...document.querySelector('mj-data-table').columns].map((c) => c.label)")
    finally:
        page.context.close()

    testbase.assert_equal(
        (headers, text[0][0], text[0][-1]),
        (["Run", "State", "Started", "Duration"], "apply · terraform ffffffff", "12m 3s"),
    )
    return
