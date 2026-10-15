"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_catalog_run_button_in_view_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Test Catalog's Trigger Run button is on screen at laptop widths (ORC-35).

.. moduleauthor:: Code Craft AI LLC

The Run action was the last of six columns, 80 rem in all, so on a real catalog at 1400 px it was scrolled out of sight and only showed at about 1700 px. It now sits beside the name and the table fits.
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
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


PROJECT: str = "0f6c2c1e-9999-4000-8000-000000000001"
PROJECTS = {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
ENTRIES = {"items": [
    {"entry_id": "0f6c2c1e-9999-4000-8000-0000000000e{}".format(number), "project_id": PROJECT, "entry_key": "ccai.tests.singlehost.checkout.test_" + name,
     "display_name": name, "retired": False, "importer_tag": "testbase-project", "created_at": "2026-10-14T23:05:00+00:00", "required_capability_tags": ["lab-browser"]}
    for number, name in enumerate(("fail", "pass"), start=1)
], "meta": {"total": 2, "page": 1, "per_page": 50}}


def _open(browser: Browser, width: int) -> Any:
    context = browser.new_context(viewport={"width": width, "height": 900})
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-catalog-bundle"],
        api_stubs={
            "/api/v1/projects": PROJECTS, "/api/v1/projects/{}/test-catalog".format(PROJECT): ENTRIES,
            "/api/v1/me/permissions": {"permissions": ["system:test_runs.create", "system:test_catalog.read", "system:test_catalog.write"]},
        },
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/test-catalog?project_id=" + PROJECT)
    page.wait_for_selector('[data-role="trigger-run"]', state="attached")
    page.wait_for_timeout(800)
    return page


def test_the_trigger_run_button_is_on_screen_at_laptop_widths(browser: Browser):
    """
    **Feature: test catalog layout (ORC-35)**
    **Property: with two entries, the Trigger Run button of each row is inside the table's visible area at 1280, 1366 and 1440 px, and the columns read Entry, Name, Action, Capabilities,
    Importer, Created.**
    """
    results = {}
    labels = []
    for width in (1280, 1366, 1440):
        page = _open(browser, width)
        try:
            results[width] = page.evaluate(
                """() => {
                    const table = document.querySelector('mj-data-table');
                    const box = table.getBoundingClientRect();
                    const buttons = [];
                    const walk = (root) => { root.querySelectorAll('[data-role="trigger-run"]').forEach((b) => buttons.push(b)); root.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) walk(e.shadowRoot); }); };
                    walk(document);
                    return buttons.map((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.left >= box.left - 1 && r.right <= box.right + 1; });
                }"""
            )
            labels = page.evaluate("() => [...document.querySelector('mj-data-table').columns].map((c) => c.label)")
        finally:
            page.context.close()

    testbase.assert_equal(
        (results, labels),
        ({1280: [True, True], 1366: [True, True], 1440: [True, True]}, ["Entry", "Name", "Action", "Capabilities", "Importer", "Created"]),
    )
    return
