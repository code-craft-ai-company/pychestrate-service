"""
.. module:: test_p30zx_bundle_table_scroll_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A bundle table wider than its page scrolls as one unit
               (ORC-25).

.. moduleauthor:: Code Craft AI LLC

``<mj-data-table>`` keeps its header row outside the scroller that holds
the rows. When the columns were wider than the page (the Runs table is
72rem of columns in a page about 67rem wide), the header row was clipped
with no way to reach it while the rows scrolled sideways on their own
scrollbar, at the bottom of a tall box: the last column was cut off
("9/26/2026, 12:12:") and the headers moved out of step with the rows.

The table's host is now the one horizontal scroll container and its grid
is as wide as its columns, so header and rows scroll together and every
column can be reached.
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


#: Narrow enough that the Runs table's six columns (72rem) cannot fit.
NARROW: Dict[str, Any] = {"viewport": {"width": 1100, "height": 800}}
WIDE: Dict[str, Any] = {"viewport": {"width": 1900, "height": 800}}

PROJECT_ID: str = "0f6c2c1e-4444-4000-8000-00000000000c"


def _runs(count: int) -> List[Dict[str, Any]]:
    rtnval: List[Dict[str, Any]] = []
    for index in range(count):
        rtnval.append({
            "run_id": "0f6c2c1e-5555-4000-8000-0000000000{:02d}".format(index),
            "project_id": PROJECT_ID,
            "state": "completed",
            "created_at": "2026-09-26T19:12:28+00:00",
            "started_at": "2026-09-26T19:12:34+00:00",
            "completed_at": "2026-09-26T19:14:41+00:00",
        })
    return rtnval


API_STUBS: Dict[str, Any] = {
    "/api/v1/runs": {"items": _runs(4), "meta": {"total": 4, "page": 1, "per_page": 25}},
    "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "slug": "orchestrate", "display_name": "Orchestrate"}]},
}

#: JS: geometry of the table host, its header cells and its first body row.
TABLE_JS: str = r"""
async () => {
  await customElements.whenDefined('mj-data-table');
  const table = document.querySelector('mj-data-table');
  const root = table.shadowRoot;
  const headers = Array.from(root.querySelectorAll('[part=header-row] .header-cell'));
  const firstRow = root.querySelector('.body-inner .row');
  const firstCells = firstRow === null ? [] : Array.from(firstRow.querySelectorAll('.cell'));
  const host = table.getBoundingClientRect();
  const lastHeader = headers[headers.length - 1].getBoundingClientRect();
  return {
    overflowX: getComputedStyle(table).overflowX,
    scrollable: table.scrollWidth > table.clientWidth + 1,
    lastHeaderRight: Math.round(lastHeader.right),
    hostRight: Math.round(host.right),
    headerCount: headers.length,
    firstHeaderLeft: Math.round(headers[0].getBoundingClientRect().left),
    firstCellLeft: firstCells.length > 0 ? Math.round(firstCells[0].getBoundingClientRect().left) : null,
    lastCellLeft: firstCells.length > 0 ? Math.round(firstCells[firstCells.length - 1].getBoundingClientRect().left) : null,
    lastHeaderLeft: Math.round(lastHeader.left),
  };
}
"""

SCROLL_END_JS: str = r"""
async () => {
  const table = document.querySelector('mj-data-table');
  const root = table.shadowRoot;
  // A person can scroll either the table or the row area, whichever
  // has a scrollbar: scroll both to the end.
  table.scrollLeft = table.scrollWidth;
  const rowScroller = root.querySelector('.body-scroll');
  rowScroller.scrollLeft = rowScroller.scrollWidth;
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const headers = Array.from(root.querySelectorAll('[part=header-row] .header-cell'));
  const firstRow = root.querySelector('.body-inner .row');
  const cells = Array.from(firstRow.querySelectorAll('.cell'));
  const host = table.getBoundingClientRect();
  return {
    lastHeaderRight: Math.round(headers[headers.length - 1].getBoundingClientRect().right),
    lastCellRight: Math.round(cells[cells.length - 1].getBoundingClientRect().right),
    hostRight: Math.round(host.right),
    headerLeft: Math.round(headers[0].getBoundingClientRect().left),
    cellLeft: Math.round(cells[0].getBoundingClientRect().left),
  };
}
"""


def _open(browser: Browser, **options: Any) -> Any:
    page = open_shell_page(
        browser,
        path="/runs",
        bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs=API_STUBS,
        **options,
    )
    page.locator("mj-data-table").first.wait_for()
    page.wait_for_function(
        "() => { const t = document.querySelector('mj-data-table');"
        " return t !== null && t.shadowRoot !== null && t.shadowRoot.querySelector('.body-inner .row') !== null; }"
    )
    return page


def test_a_table_wider_than_the_page_scrolls_as_one_unit(browser: Browser):
    """
    **Feature: bundle tables (ORC-25)**
    **Property: the Runs table, whose columns are wider than the page,
    is a horizontal scroll container itself.**
    """
    page = _open(browser, **NARROW)
    try:
        found = page.evaluate(TABLE_JS)
        testbase.assert_equal((found["overflowX"], found["scrollable"]), ("auto", True), str(found))
    finally:
        page.context.close()
    return


def test_every_column_can_be_reached_by_scrolling(browser: Browser):
    """
    **Feature: bundle tables (ORC-25)**
    **Property: scrolled to the end, the last header and the last body
    cell are inside the table's box, so no column is cut off.**
    """
    page = _open(browser, **NARROW)
    try:
        found = page.evaluate(SCROLL_END_JS)
        testbase.assert_equal(
            (found["lastHeaderRight"] <= found["hostRight"] + 1, found["lastCellRight"] <= found["hostRight"] + 1),
            (True, True),
            str(found),
        )
    finally:
        page.context.close()
    return


def test_the_header_and_the_rows_scroll_together(browser: Browser):
    """
    **Feature: bundle tables (ORC-25)**
    **Property: scrolled sideways, the first header cell and the first
    body cell stay in the same column: their left edges are equal.**
    """
    page = _open(browser, **NARROW)
    try:
        found = page.evaluate(SCROLL_END_JS)
        testbase.assert_equal(found["headerLeft"], found["cellLeft"], str(found))
    finally:
        page.context.close()
    return


def test_a_wide_page_does_not_scroll_the_table(browser: Browser):
    """
    **Feature: bundle tables (ORC-25)**
    **Property: on a page wide enough for every column, the table does
    not scroll and its last column ends inside the box.**
    """
    page = _open(browser, **WIDE)
    try:
        found = page.evaluate(TABLE_JS)
        testbase.assert_equal(
            (found["scrollable"], found["lastHeaderRight"] <= found["hostRight"] + 1),
            (False, True),
            str(found),
        )
    finally:
        page.context.close()
    return
