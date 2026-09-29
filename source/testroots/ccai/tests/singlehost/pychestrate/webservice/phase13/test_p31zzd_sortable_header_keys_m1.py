"""
.. module:: test_p31zzd_sortable_header_keys_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A sortable table header sorts from the keyboard (ORC-24, WCAG 2.1.1).

.. moduleauthor:: Code Craft AI LLC

The vendored ``<mj-data-table>`` sorts a column only when its header cell is
clicked (its keyboard handling covers the arrows, Home, End and Escape), so
Enter and Space on a focused header did nothing. The shell now gives every
table the standard behaviour. A real table is built in a browser with two
sortable columns, a header cell is focused, and the keys are pressed.
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
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

BUILD_TABLE_JS: str = """() => {
    const table = document.createElement('mj-data-table');
    table.setAttribute('sortable', '');
    table.columns = [{key: 'name', label: 'Name'}, {key: 'size', label: 'Size'}];
    table.rows = [{name: 'b', size: 2}, {name: 'a', size: 3}, {name: 'c', size: 1}];
    document.body.appendChild(table);
    return true;
}"""


def _open_table(browser: Browser) -> Any:
    page = open_shell_page(browser, **DESKTOP)
    page.evaluate(BUILD_TABLE_JS)
    page.wait_for_selector('.header-cell[data-sortable="true"]', timeout=5000)
    return page


def test_enter_and_space_on_a_sortable_header_sort_the_column(browser: Browser):
    """
    **Feature: keyboard sorting (WCAG 2.1.1)**
    **Property: with a sortable header cell focused, Enter sorts ascending,
    Space then flips it to descending, and a mouse click on the other
    column still works; aria-sort follows.**
    """
    page = _open_table(browser)
    try:
        name = page.locator('.header-cell[data-col-key="name"]')
        name.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        after_enter = name.get_attribute("aria-sort")
        page.keyboard.press("Space")
        page.wait_for_timeout(200)
        after_space = name.get_attribute("aria-sort")
        size = page.locator('.header-cell[data-col-key="size"]')
        size.click()
        page.wait_for_timeout(200)
        after_click = size.get_attribute("aria-sort")
    finally:
        page.context.close()

    testbase.assert_equal((after_enter, after_space, after_click), ("ascending", "descending", "ascending"))
    return


def test_other_keys_and_a_page_scroll_key_do_not_sort(browser: Browser):
    """
    **Feature: keyboard sorting (WCAG 2.1.1)**
    **Property: a letter key on a focused header does not sort it, and
    pressing Space in a text input elsewhere on the page is untouched.**
    """
    page = _open_table(browser)
    try:
        name = page.locator('.header-cell[data-col-key="name"]')
        name.focus()
        page.keyboard.press("a")
        page.wait_for_timeout(150)
        after_letter = name.get_attribute("aria-sort")
        page.evaluate("() => { const i = document.createElement('input'); i.id = 'plain'; document.body.appendChild(i); i.focus(); }")
        page.keyboard.type("a b")
        typed = page.evaluate("document.getElementById('plain').value")
    finally:
        page.context.close()

    testbase.assert_equal((after_letter, typed), ("none", "a b"))
    return
