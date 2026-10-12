"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_extension_packs_listed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Extension Registry lists the installed packs and the ones that did not load (DOC-11).

.. moduleauthor:: Code Craft AI LLC

A pack that fails to load is logged and the service starts without it, so the page that lists the extensions gave no sign that one
the person installed was missing. It now has an "Extension packs" section: one line saying how many loaded, and a row per pack with its
state and, for a pack that did not load, the error. The page is opened in a browser against stubbed API answers.
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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

ROUTE = {
    "ext_name": "example", "full_path": "/api/v1/ext/example/echo", "required_permissions": [], "required_capabilities": [],
    "handler_class": "ExampleEcho", "mounted": True,
}


def _open(browser: Browser, **fields: Any) -> Dict[str, Any]:
    body: Dict[str, Any] = {"items": [ROUTE], "total": 1, "dynamic_mount": "mounted"}
    body.update(fields)
    page = open_shell_page(
        browser, path="/admin/extensions", bundle_names=["pyc-site-shell", "pyc-admin-bundle"], api_stubs={"/api/v1/ext": body}, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="packs"]')
        page.wait_for_timeout(400)
        rows: List[Dict[str, Any]] = page.evaluate(
            """() => [...document.querySelectorAll('[data-role=pack-row]')].map((row) => ({
                state: row.getAttribute('data-state'),
                name: row.querySelector('strong').textContent,
                chip: row.querySelector('mj-chip').textContent.trim(),
                tone: row.querySelector('mj-chip').getAttribute('data-tone'),
                target: (row.querySelector('code') || {}).textContent || '',
                error: (row.querySelector('[data-role=pack-error]') || {}).textContent || '',
            }))"""
        )
        summary = page.locator('[data-role="packs-summary"], [data-role="packs-none"], [data-role="packs-off"]').first
        return {
            "rows": rows,
            "summary_role": summary.get_attribute("data-role"),
            "summary": " ".join(summary.inner_text().split()),
            "routes_table": page.locator("mj-data-table").count(),
            "empty": page.locator('[data-role="empty-state"]').count(),
        }
    finally:
        page.context.close()


def test_a_pack_that_did_not_load_is_named_with_its_error(browser: Browser):
    """
    **Feature: extension packs listed (DOC-11)**
    **Property: with one loaded and one failed pack the page says "1 of 2 installed packs did not load. The service started without it.",
    lists the loaded pack with a green "Loaded" chip and the failed one with a red "Did not load" chip, its entry point and its error.**
    """
    found = _open(browser, packs_enabled=True, packs=[
        {"name": "demo-notes", "target": "demo_notes.register:register", "loaded": True, "error": ""},
        {"name": "lab-power", "target": "lab_power:register", "loaded": False, "error": "ImportError: No module named 'pyvisa'"},
    ])

    testbase.assert_equal(
        (found["summary_role"], found["summary"], found["rows"], found["routes_table"]),
        (
            "packs-summary", "1 of 2 installed packs did not load. The service started without it.",
            [
                {"state": "loaded", "name": "demo-notes", "chip": "Loaded", "tone": "ok", "target": "demo_notes.register:register", "error": ""},
                {"state": "failed", "name": "lab-power", "chip": "Did not load", "tone": "error", "target": "lab_power:register",
                 "error": "ImportError: No module named 'pyvisa'"},
            ],
            1,
        ),
    )
    return


def test_loaded_none_and_switched_off_each_say_so(browser: Browser):
    """
    **Feature: extension packs listed (DOC-11)**
    **Property: all packs loaded reads "All 2 installed packs loaded." (one: "The installed pack loaded."), none installed reads "No extension
    packs are installed.", and loading switched off reads that no pack was loaded; none of them lists a row for a missing pack.**
    """
    two = _open(browser, packs_enabled=True, packs=[
        {"name": "a", "target": "a:register", "loaded": True, "error": ""}, {"name": "b", "target": "b:register", "loaded": True, "error": ""},
    ])
    one = _open(browser, packs_enabled=True, packs=[{"name": "a", "target": "a:register", "loaded": True, "error": ""}])
    none = _open(browser, packs_enabled=True, packs=[])
    off = _open(browser, packs_enabled=False, packs=[])

    testbase.assert_equal(
        (
            (two["summary"], len(two["rows"])), (one["summary"], len(one["rows"])),
            (none["summary_role"], none["summary"], len(none["rows"])),
            (off["summary_role"], off["summary"], len(off["rows"])),
        ),
        (
            ("All 2 installed packs loaded.", 2), ("The installed pack loaded.", 1),
            ("packs-none", "No extension packs are installed.", 0),
            ("packs-off", "Loading installed extension packs is turned off on this service, so none were loaded.", 0),
        ),
    )
    return


def test_the_packs_show_even_when_no_extension_adds_a_route(browser: Browser):
    """
    **Feature: extension packs listed (DOC-11)**
    **Property: with no extension routes the page still shows the packs section (a failed pack is the likeliest reason there are none) above
    the empty state, and an older service that sends no ``packs`` field reads as no packs installed.**
    """
    failed = _open(browser, items=[], total=0, packs_enabled=True, packs=[
        {"name": "lab-power", "target": "lab_power:register", "loaded": False, "error": "ImportError: boom"},
    ])
    older = _open(browser)

    testbase.assert_equal(
        (failed["empty"], failed["routes_table"], [row["state"] for row in failed["rows"]], older["summary_role"], older["summary"]),
        (1, 0, ["failed"], "packs-none", "No extension packs are installed."),
    )
    return
