"""
.. module:: test_p30z_narrow_fragment_layout_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Server-rendered pages do not clip their content on a
               phone (RES-15, PRJ-14).

.. moduleauthor:: Code Craft AI LLC

On a 390px screen every projects and resources page ran to about 500
to 660px inside a shell that hides horizontal overflow, so filters,
buttons, table columns and values were cut off with no scrollbar. The
stacked sub-navigation layout kept ``align-items: flex-start``, which
sizes each child to its content instead of to the column; wide tables
had nothing to scroll them; the two-column and detail grids used
``1fr`` tracks, which cannot shrink below their content; and the
sub-navigation's 10 to 16 links filled the first screen. The fragment
stylesheet now stretches the column, scrolls tables on narrow screens,
lets grid tracks shrink, and lays the sub-navigation out as one
scrolling row.
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
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


PHONE: Dict[str, Any] = {
    "viewport": {"width": 390, "height": 844},
    "has_touch": True,
    "is_mobile": True,
}
DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

#: A projects / resources style page: a long sub-navigation beside the
#: content, a card holding a wide table, the two-column and detail grids
#: with unbreakable text, and a card grid of the kind the dashboards use.
FRAGMENT_JS: str = r"""
() => {
  const main = document.querySelector('main.pyc-site-shell__main');
  const links = Array.from({length: 14}, (_, i) => '<li><a href="/x' + i + '">Section number ' + i + '</a></li>').join('');
  const cells = Array.from({length: 9}, (_, i) => '<th>Column ' + i + '</th>').join('');
  const values = Array.from({length: 9}, (_, i) => '<td>value-that-is-quite-long-' + i + '</td>').join('');
  const unbroken = 'x'.repeat(120);
  const fragment = document.createElement('section');
  fragment.className = 'pyc-admin-page-fragment projects-fragment';
  fragment.innerHTML = [
    '<div class="pyc-subnav-layout">',
    '<nav class="pyc-subnav" aria-label="Section"><ul>' + links + '</ul></nav>',
    '<div class="pyc-subnav-layout__content">',
    '<div class="page-header"><h1>Devices</h1></div>',
    '<div class="card"><table class="data-table" data-probe="table"><thead><tr>' + cells + '</tr></thead>',
    '<tbody><tr>' + values + '</tr></tbody></table></div>',
    '<div class="two-col"><div class="card"><code>' + unbroken + '</code></div><div class="card">B</div></div>',
    '<div class="detail-grid"><div class="card"><code>' + unbroken + '</code></div><div class="card">D</div></div>',
    '</div></div>',
  ].join('');
  main.appendChild(fragment);
  return true;
}
"""

#: JS: the elements inside the fragment whose right edge lies beyond the
#: viewport and that no horizontally scrolling ancestor can reveal.
CLIPPED_JS: str = r"""
() => {
  const viewport = document.documentElement.clientWidth;
  const fragment = document.querySelector('.pyc-admin-page-fragment');
  const clipped = [];
  for (const el of fragment.querySelectorAll('*')) {
    const box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0 || box.right <= viewport + 1) {
      continue;
    }
    let ancestor = el.parentElement;
    let scrolls = false;
    while (ancestor !== null && ancestor !== document.body) {
      const overflow = getComputedStyle(ancestor).overflowX;
      if (overflow === 'auto' || overflow === 'scroll') {
        scrolls = true;
        break;
      }
      ancestor = ancestor.parentElement;
    }
    if (scrolls === false) {
      clipped.push(el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0]);
    }
  }
  return clipped.slice(0, 6);
}
"""


def _open_with_fragment(browser: Browser, **context_options: Any) -> Any:
    page = open_shell_page(browser, **context_options)
    page.evaluate(FRAGMENT_JS)
    page.wait_for_timeout(200)
    return page


def test_nothing_in_the_fragment_is_clipped_on_a_phone(browser: Browser):
    """
    **Feature: narrow-screen layout (RES-15)**
    **Property: at 390px no element of a projects / resources style
    page extends beyond the screen unless a scrolling ancestor can
    reveal it.**
    """
    page = _open_with_fragment(browser, **PHONE)
    try:
        testbase.assert_equal(page.evaluate(CLIPPED_JS), [])
    finally:
        page.context.close()
    return


def test_a_wide_table_scrolls_sideways_on_a_phone(browser: Browser):
    """
    **Feature: narrow-screen layout (RES-15)**
    **Property: at 390px a table wider than the screen scrolls inside
    its own box: its scroll width exceeds its client width and its
    overflow is auto.**
    """
    page = _open_with_fragment(browser, **PHONE)
    try:
        found = page.evaluate(
            "() => { const t = document.querySelector('[data-probe=table]');"
            " return {scrolls: t.scrollWidth > t.clientWidth + 1, overflow: getComputedStyle(t).overflowX}; }"
        )
        testbase.assert_equal(found, {"scrolls": True, "overflow": "auto"})
    finally:
        page.context.close()
    return


def test_the_sub_navigation_does_not_fill_the_first_phone_screen(browser: Browser):
    """
    **Feature: narrow-screen layout (RES-15)**
    **Property: at 390px a 14-link sub-navigation is one row of at most
    80px, not a column that pushes the page below the fold.**
    """
    page = _open_with_fragment(browser, **PHONE)
    try:
        height = page.evaluate("() => document.querySelector('.pyc-subnav').getBoundingClientRect().height")
        testbase.assert_equal(height <= 80, True, "sub-navigation is {}px tall".format(height))
    finally:
        page.context.close()
    return


def test_a_table_stays_full_width_on_a_desktop(browser: Browser):
    """
    **Feature: narrow-screen layout (RES-15)**
    **Property: at 1440px the narrow-screen table rule does not apply:
    the table is a normal table as wide as its card.**
    """
    page = _open_with_fragment(browser, **DESKTOP)
    try:
        found = page.evaluate(
            "() => { const t = document.querySelector('[data-probe=table]');"
            " const card = t.parentElement;"
            " return {display: getComputedStyle(t).display,"
            " full: Math.abs(t.getBoundingClientRect().width - (card.clientWidth - 40)) < 45}; }"
        )
        testbase.assert_equal(found["display"], "table")
        testbase.assert_equal(found["full"], True)
    finally:
        page.context.close()
    return


def _blueprints_root() -> str:
    rtnval = os.path.join(os.path.dirname(SITE_DIRECTORIES.DIR_STATIC), "blueprints")
    return rtnval


def _fragment_templates() -> List[str]:
    root = _blueprints_root()
    rtnval: List[str] = []
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".html") is True:
                rtnval.append(os.path.join(folder, name))
    return rtnval


#: Templates that are allowed a fixed grid: the month calendar is a seven
#: column grid by nature and needs its own narrow-screen design.
FIXED_GRID_ALLOWED: List[str] = [os.path.join("projects", "templates", "projects", "calendar", "view.html")]


def test_no_fragment_template_sets_a_fixed_grid_track():
    """
    **Feature: narrow-screen layout (RES-15)**
    **Property: no server-rendered template gives a grid a bare
    minmax(NNNpx, 1fr) track or a fixed repeat(N, 1fr) count, which
    cannot shrink to a phone; they use minmax(min(NNNpx, 100%), 1fr)
    with auto-fit. (The month calendar is the one exception.)**
    """
    offenders: List[str] = []
    for path in _fragment_templates():
        relative = os.path.relpath(path, _blueprints_root())
        if relative in FIXED_GRID_ALLOWED:
            continue
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        if (
            re.search(r"minmax\(\s*\d+px\s*,\s*1fr\s*\)", text) is not None
            or re.search(r"repeat\(\s*\d+\s*,\s*1fr\s*\)", text) is not None
        ):
            offenders.append(relative)
    testbase.assert_equal(offenders, [])
    return
