"""
.. module:: test_p30d_mj_components_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Browser regressions for the served component library
               (pyc-mj-lib): project pickers, pagers, catalog strings,
               and combobox names.

.. moduleauthor:: Code Craft AI LLC

Each test drives the committed ``pyc-mj-lib/index.js`` (and, for the
product-level tests, the real test-catalog bundle inside the real
shell document) in headless Chromium. Requests never leave the
process: :mod:`_shell_browser_harness` fulfils them from the static
tree and from stubbed API answers, so no pychestrate instance is
needed.

Covered audit findings: ORC-02 (``mj-select`` ignored options added
after its first render), ORC-03 (``mj-pagination`` ignored
``total-items``), LD-04 (raw ``mj.*`` catalog keys on screen), ORC-22
(unnamed comboboxes).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    RAW_CATALOG_KEYS_JS,
    open_fixture_page,
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


CATALOG_BUNDLES: List[str] = ["pyc-site-shell", "pyc-catalog-bundle"]
CATALOG_ENTRY_COUNT: int = 31

PROJECTS_BODY: Dict[str, Any] = {
    "items": [
        {"project_id": "p-alpha", "slug": "alpha", "display_name": "Alpha Project"},
        {"project_id": "p-bravo", "slug": "bravo", "display_name": "Bravo Project"},
    ],
    "meta": {"total": 2, "page": 1, "per_page": 50},
}


def _catalog_page(query: Dict[str, str]) -> Dict[str, Any]:
    """
        Stub for ``GET /api/v1/projects/p-alpha/test-catalog``: 31
        entries paged by the ``page`` / ``per_page`` query.
    """
    page = int(query.get("page", "1"))
    per_page = int(query.get("per_page", "25"))
    entries = []
    for index in range(CATALOG_ENTRY_COUNT):
        entries.append({
            "entry_id": "e-{:02d}".format(index),
            "project_id": "p-alpha",
            "entry_key": "case-{:02d}".format(index),
            "display_name": "Seed case {:02d}".format(index),
            "importer_tag": "seed",
            "required_capability_tags": [],
            "retired": False,
            "created_at": "2026-09-22T12:00:00+00:00",
        })
    start = (page - 1) * per_page
    rtnval = {
        "items": entries[start:start + per_page],
        "meta": {"total": CATALOG_ENTRY_COUNT, "page": page, "per_page": per_page},
    }
    return rtnval


def _open_catalog(browser: Browser) -> Any:
    """
        Open ``/test-catalog`` with two projects and 31 catalog entries
        and wait for the first page of rows.

        :returns: The page.
    """
    page = open_shell_page(
        browser,
        path="/test-catalog",
        bundle_names=CATALOG_BUNDLES,
        api_stubs={
            "/api/v1/projects": PROJECTS_BODY,
            "/api/v1/projects/p-alpha/test-catalog": _catalog_page,
        },
    )
    page.wait_for_function(
        "() => { const pager = document.querySelector('pyc-test-catalog mj-pagination'); "
        "return pager !== null && pager.getAttribute('total-items') === '31'; }"
    )
    return page


# ---------------------------------------------------------------------------
# ORC-02: pickers render options that arrive after their first render
# ---------------------------------------------------------------------------


def test_catalog_project_picker_lists_every_project(browser: Browser):
    """
    **Feature: component library -- mj-select dynamic options**
    **Property: on /test-catalog the project picker offers both
    projects the projects fetch returned (the options arrive after the
    picker first rendered).**
    """
    page = _open_catalog(browser)
    try:
        page.wait_for_function(
            "() => { const select = document.querySelector('pyc-test-catalog mj-select[data-role=\"project-select\"]'); "
            "return select !== null && select.shadowRoot.querySelectorAll('.option').length === 2; }"
        )
        labels = page.evaluate(
            "() => Array.from(document.querySelector('pyc-test-catalog mj-select[data-role=\"project-select\"]')"
            ".shadowRoot.querySelectorAll('.option-label')).map((node) => node.textContent)"
        )
        testbase.assert_equal(labels, ["Alpha Project", "Bravo Project"])
    finally:
        page.context.close()
    return


def test_catalog_project_picker_shows_the_selected_project(browser: Browser):
    """
    **Feature: component library -- mj-select dynamic options**
    **Property: the project picker's trigger shows the selected
    project's name instead of staying empty.**
    """
    page = _open_catalog(browser)
    try:
        page.wait_for_function(
            "() => document.querySelector('pyc-test-catalog mj-select[data-role=\"project-select\"]')"
            ".shadowRoot.querySelector('.trigger .label').textContent === 'Alpha Project'"
        )
    finally:
        page.context.close()
    return


def test_select_renders_options_appended_after_first_render(browser: Browser):
    """
    **Feature: component library -- mj-select dynamic options**
    **Property: <mj-option> children appended to a rendered mj-select
    appear in its listbox.**
    """
    page = open_fixture_page(browser, body_html='<mj-select id="picker" label="Project"></mj-select>')
    try:
        page.evaluate(
            "() => { const select = document.querySelector('#picker'); "
            "for (const [value, label] of [['a', 'Alpha'], ['b', 'Bravo']]) { "
            "const option = document.createElement('mj-option'); option.setAttribute('value', value); "
            "option.textContent = label; select.appendChild(option); } }"
        )
        page.wait_for_function(
            "() => document.querySelector('#picker').shadowRoot.querySelectorAll('.option').length === 2"
        )
    finally:
        page.context.close()
    return


def test_select_option_label_is_text_not_markup(browser: Browser):
    """
    **Feature: component library -- mj-select dynamic options**
    **Property: an option label that contains markup (a project name
    is user data) is rendered as text, never parsed into elements.**
    """
    page = open_fixture_page(browser, body_html='<mj-select id="picker" label="Project"></mj-select>')
    try:
        page.evaluate(
            "() => { const option = document.createElement('mj-option'); option.setAttribute('value', 'x'); "
            "option.textContent = '<img src=x onerror=\"window.__injected = 1\">Bravo'; "
            "document.querySelector('#picker').appendChild(option); }"
        )
        page.wait_for_function(
            "() => document.querySelector('#picker').shadowRoot.querySelectorAll('.option').length === 1"
        )
        parsed = page.evaluate(
            "() => document.querySelector('#picker').shadowRoot.querySelector('.option-label img') !== null"
        )
        testbase.assert_equal(parsed, False)
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# ORC-22: comboboxes have accessible names
# ---------------------------------------------------------------------------


def test_catalog_project_combobox_is_named_project(browser: Browser):
    """
    **Feature: component library -- mj-select accessible name**
    **Property: the /test-catalog project picker is a combobox named
    "Project" (from the host label attribute).**
    """
    page = _open_catalog(browser)
    try:
        count = page.get_by_role("combobox", name="Project", exact=True).count()
        testbase.assert_equal(count, 1)
    finally:
        page.context.close()
    return


def test_select_wrapped_in_label_is_named_by_the_label(browser: Browser):
    """
    **Feature: component library -- mj-select accessible name**
    **Property: an mj-select inside a <label> (the metrics views'
    pattern) is a combobox named by the label text alone.**
    """
    page = open_fixture_page(
        browser,
        body_html='<label>Metric <mj-select><mj-option value="cpu">cpu.usage</mj-option></mj-select></label>',
    )
    try:
        count = page.get_by_role("combobox", name="Metric", exact=True).count()
        testbase.assert_equal(count, 1)
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# ORC-03: pagers derive their page count from total-items
# ---------------------------------------------------------------------------


def test_catalog_pager_offers_the_second_page(browser: Browser):
    """
    **Feature: component library -- mj-pagination page count**
    **Property: with 31 catalog entries at 25 per page, the pager
    shows page buttons 1 and 2.**
    """
    page = _open_catalog(browser)
    try:
        labels = page.evaluate(
            "() => Array.from(document.querySelector('pyc-test-catalog mj-pagination').shadowRoot"
            ".querySelectorAll('.page-btn')).map((node) => node.textContent.trim())"
        )
        testbase.assert_equal(labels, ["1", "2"])
    finally:
        page.context.close()
    return


def test_catalog_next_page_shows_the_remaining_entries(browser: Browser):
    """
    **Feature: component library -- mj-pagination page count**
    **Property: activating Next on /test-catalog loads page 2 and shows
    entries 26-31.**
    """
    page = _open_catalog(browser)
    try:
        page.locator("pyc-test-catalog mj-pagination").get_by_role("button", name="Next", exact=True).click()
        page.wait_for_function(
            "() => { const table = document.querySelector('pyc-test-catalog mj-data-table'); "
            "return table !== null && Array.isArray(table.rows) && table.rows.length === 6 "
            "&& table.rows[5].entry_key === 'case-30'; }"
        )
    finally:
        page.context.close()
    return


def test_pager_hides_itself_when_everything_fits_on_one_page(browser: Browser):
    """
    **Feature: component library -- mj-pagination page count**
    **Property: a pager whose items fit on one page is hidden, even
    when the page styles the host display: flex.**
    """
    page = open_fixture_page(
        browser,
        body_html=(
            '<mj-pagination id="pager" style="display: flex" page="1" page-size="25" total-items="0">'
            '</mj-pagination>'
        ),
    )
    try:
        visible = page.locator("#pager").is_visible()
        testbase.assert_equal(visible, False)
    finally:
        page.context.close()
    return


def test_pager_summarizes_the_visible_range(browser: Browser):
    """
    **Feature: component library -- mj-pagination page count**
    **Property: the catalog pager reads "Showing 1–25 of 31".**
    """
    page = _open_catalog(browser)
    try:
        summary = page.evaluate(
            "() => document.querySelector('pyc-test-catalog mj-pagination').shadowRoot"
            ".querySelector('.summary').textContent"
        )
        testbase.assert_equal(summary, "Showing 1–25 of 31")
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# LD-04: no raw "mj.*" catalog keys
# ---------------------------------------------------------------------------


def test_catalog_view_shows_no_raw_catalog_keys(browser: Browser):
    """
    **Feature: component library -- catalog strings**
    **Property: nothing on /test-catalog (text or aria-label, shadow
    DOM included) shows a raw "mj.<component>.<key>" string.**
    """
    page = _open_catalog(browser)
    try:
        found = page.evaluate(RAW_CATALOG_KEYS_JS)
        testbase.assert_equal(found, [])
    finally:
        page.context.close()
    return


def test_pager_buttons_read_previous_and_next(browser: Browser):
    """
    **Feature: component library -- catalog strings**
    **Property: the pager's buttons are named "Previous" and "Next" and
    its landmark "Pagination".**
    """
    page = open_fixture_page(
        browser,
        body_html='<mj-pagination page="2" page-size="25" total-items="80"></mj-pagination>',
    )
    try:
        names = [
            page.get_by_role("button", name="Previous", exact=True).count(),
            page.get_by_role("button", name="Next", exact=True).count(),
            page.get_by_role("navigation", name="Pagination", exact=True).count(),
        ]
        testbase.assert_equal(names, [1, 1, 1])
    finally:
        page.context.close()
    return


def test_every_catalog_key_in_the_bundle_has_a_default_string():
    """
    **Feature: component library -- catalog strings**
    **Property: every "mj.<component>.<key>" literal in the served
    pyc-mj-lib bundle is registered in the library's default string
    table, so no component can fall back to showing the key.**
    """
    bundle_path = os.path.join(
        SITE_DIRECTORIES.DIR_STATIC, "javascript", "pyc-mj-lib", "index.js"
    )
    with open(bundle_path, "r", encoding="utf-8") as fh:
        bundle = fh.read()
    keys = set(re.findall(r"[\"'](mj\.[a-zA-Z]+\.[a-zA-Z]+)[\"']", bundle))
    unregistered = sorted(
        key for key in keys
        if re.search(r"[\"']" + re.escape(key) + r"[\"']\s*:", bundle) is None
    )
    testbase.assert_true(len(keys) > 0, "no mj.* catalog keys found in the bundle")
    testbase.assert_equal(unregistered, [])
    return
