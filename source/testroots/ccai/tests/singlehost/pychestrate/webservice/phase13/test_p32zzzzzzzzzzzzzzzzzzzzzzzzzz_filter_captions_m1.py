"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzz_filter_captions_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every filter on the list pages is captioned (ORC-42).

.. moduleauthor:: Code Craft AI LLC

``<mj-select label="State">`` is named for assistive technology but drawn visually hidden, so the filter bars of Runs, Builds,
Pipelines and the Test Catalog showed unlabelled drop-downs while Environments, Provisioning, Clients and Pods wrote the
name above each. All of them now caption each filter, in the same small muted type. The pages are opened in a browser against
stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Tuple

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

PROJECT: str = "0f6c2c1e-1111-4000-8000-000000000001"
PROJECTS = {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}

#: (page, bundle, the captions the page's selects carry, left to right)
PAGES: List[Tuple[str, str, List[str]]] = [
    ("/runs?project_id=" + PROJECT, "pyc-runs-bundle", ["State", "Project"]),
    ("/builds?project_id=" + PROJECT, "pyc-builds-bundle", ["Project", "State"]),
    ("/pipelines?project_id=" + PROJECT, "pyc-pipelines-bundle", ["Project"]),
    ("/test-catalog?project_id=" + PROJECT, "pyc-catalog-bundle", ["Project"]),
    ("/environments?project_id=" + PROJECT, "pyc-infra-bundle", ["Project", "State"]),
    ("/provisioning-runs?project_id=" + PROJECT, "pyc-infra-bundle", ["Project", "State"]),
    ("/clients?project_id=" + PROJECT, "pyc-pods-bundle", ["Project", "Status", "Liveness"]),
    ("/pods?project_id=" + PROJECT, "pyc-pods-bundle", ["Project"]),
]

#: For each ``mj-select`` in the page's main region: the visible text written in its field wrapper before it.
_CAPTIONS_JS = """() => {
    const out = [];
    for (const select of document.querySelectorAll('main mj-select')) {
        let wrapper = select.parentElement;
        let caption = '';
        for (const node of wrapper.childNodes) {
            if (node === select) { break; }
            const text = (node.textContent || '').trim();
            const hidden = node.nodeType === 1 && (node.hidden === true || getComputedStyle(node).display === 'none');
            if (text.length > 0 && hidden === false) { caption = text; break; }
        }
        out.push(caption);
    }
    return out;
}"""


def test_every_filter_select_on_the_list_pages_has_a_visible_caption(browser: Browser):
    """
    **Feature: filter bars (ORC-42)**
    **Property: on Runs, Builds, Pipelines, the Test Catalog, Environments, Provisioning, Clients and Pods each drop-down
    filter is captioned above it with its name (Project, State, Status, Liveness), left to right as listed; none is bare.**
    """
    found: Dict[str, List[str]] = {}
    for path, bundle, _expected in PAGES:
        page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP)
        try:
            page.wait_for_selector("main mj-select")
            page.wait_for_timeout(1500)
            found[path] = [caption for caption in page.evaluate(_CAPTIONS_JS)]
        finally:
            page.context.close()

    testbase.assert_equal(found, {path: expected for path, _bundle, expected in PAGES})
    return


def test_the_caption_is_not_read_twice(browser: Browser):
    """
    **Feature: filter bars (ORC-42)**
    **Property: on the Runs page the State filter keeps its accessible name ("State") and the visible caption beside it is
    hidden from assistive technology.**
    """
    page = open_shell_page(browser, path="/runs?project_id=" + PROJECT, bundle_names=["pyc-site-shell", "pyc-runs-bundle"], api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP)
    try:
        page.wait_for_selector('[data-role="state-filter"]')
        page.wait_for_timeout(1000)
        state = page.evaluate(
            """() => {
                const select = document.querySelector('[data-role=state-filter]');
                const caption = select.parentElement.querySelector('.pyc-filter-caption');
                return [select.getAttribute('label'), caption.getAttribute('aria-hidden'), caption.textContent];
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(state, ["State", "true", "State"])
    return


def test_the_as_of_stamp_and_the_csv_link_sit_level_with_the_buttons(browser: Browser):
    """
    **Feature: filter bars (ORC-42, ORC-48)**
    **Property: with captions above the filters, the small "as of" stamp (Runs, Clients, Pods) and the Runs page's Download CSV
    link are level with the middle of the Refresh button beside them (their vertical centres are within 4px), not with the
    middle of the whole captioned row.**
    """
    cases = [
        ("/runs?project_id=" + PROJECT, "pyc-runs-bundle", ["/api/v1/runs"], [".pyc-runs-list__stamp", ".pyc-runs-list__export-link"]),
        ("/clients?project_id=" + PROJECT, "pyc-pods-bundle", ["/api/v1/clients"], [".pyc-clients-list__stamp"]),
        ("/pods?project_id=" + PROJECT, "pyc-pods-bundle", ["/api/v1/projects/{}/pod-definitions".format(PROJECT)], [".pyc-pods-list__stamp"]),
    ]
    offsets: Dict[str, List[int]] = {}
    for path, bundle, lists, selectors in cases:
        stubs: Dict[str, Any] = {"/api/v1/projects": PROJECTS}
        for url in lists:
            stubs[url] = {"items": [], "meta": {"total": 0}} if url.endswith("/runs") else []
        page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs=stubs, **DESKTOP)
        try:
            page.wait_for_selector('[data-role="refresh"]')
            page.wait_for_timeout(2000)
            offsets[path] = page.evaluate(
                """(selectors) => {
                    const button = document.querySelector('[data-role=refresh]').getBoundingClientRect();
                    const middle = button.top + button.height / 2;
                    return selectors.map((selector) => {
                        const box = document.querySelector(selector).getBoundingClientRect();
                        return Math.abs(Math.round(box.top + box.height / 2 - middle));
                    });
                }""",
                selectors,
            )
        finally:
            page.context.close()

    testbase.assert_equal({path: all(offset <= 4 for offset in found) for path, found in offsets.items()}, {path: True for path, _b, _l, _s in cases})
    return
