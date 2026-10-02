"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzz_table_cells_keep_words_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A table that is a little too wide does not cut short words or buttons in half (XC-05).

.. moduleauthor:: Code Craft AI LLC

The server-rendered tables let every cell break "anywhere" so a long address would not widen the table. That also let the browser
shrink every column toward one character when a table was only a little too wide: on the All Projects list "Orchestrate" and
"admin" were cut in two, and on the user and role lists the "Edit", "Copy" and "Deactivate" buttons were. A column of short values is marked (``nowrap``, ``min-name``) so the description column absorbs the squeeze, and buttons
never break; a long unbroken value still wraps inside its cell. A table in the shell's
admin-page style is built in a browser and made narrower than its content.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1300, "height": 700}}

TABLE = """
<div class="pyc-admin-page-fragment"><div class="table-scroll">
<table class="data-table">
  <thead><tr><th scope="col">Name</th><th scope="col">Description</th><th scope="col">Owner</th><th scope="col">Members</th><th scope="col">Repositories</th><th scope="col">Last Activity</th><th scope="col">Actions</th></tr></thead>
  <tbody>
    <tr>
      <td class="min-name"><a href="/projects/1">Orchestrate</a></td>
      <td>Collections of python packages used for testing an...</td>
      <td class="nowrap">admin</td><td class="nowrap">12</td><td class="nowrap">3</td><td class="nowrap">2026-08-08 07:00 UTC</td>
      <td><a class="btn btn-sm btn-secondary" href="#">View</a> <a class="btn btn-sm btn-secondary" href="#">Edit</a></td>
    </tr>
  </tbody>
</table>
</div>
<div class="table-scroll">
<table class="data-table">
  <thead><tr><th scope="col">Username</th><th scope="col">Email</th><th scope="col">Display Name</th><th scope="col">Status</th><th scope="col">Roles</th><th scope="col">Actions</th></tr></thead>
  <tbody>
    <tr>
      <td class="min-name"><a href="/admin/users/1">system-admin</a></td><td>admin@example.com</td><td>System Administrator</td><td>active</td><td>administrator, viewer</td>
      <td><div class="row-actions"><a class="btn btn-sm btn-secondary" href="#">Edit</a> <a class="btn btn-sm btn-secondary" href="#">Deactivate</a> <a class="btn btn-sm btn-secondary" href="#">Copy</a> <a class="btn btn-sm btn-secondary" href="#">Delete</a></div></td>
    </tr>
  </tbody>
</table>
</div></div>
"""

#: The words (four or more characters, whitespace separated) of the cells and buttons that must stay whole (a marked column
#: of short values, a header, a button) that are laid out over more than one line. A long description or an email may wrap.
_BROKEN_WORDS_JS = """() => {
  const broken = [];
  for (const cell of document.querySelectorAll('main table td.min-name, main table td.nowrap, main table th, main table .btn')) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const pattern = /\\S+/g; let match;
      while ((match = pattern.exec(node.textContent)) !== null) {
        if (match[0].length < 4 || match[0].indexOf('-') >= 0) { continue; }
        const range = document.createRange(); range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
        const tops = new Set([...range.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top)));
        if (tops.size > 1) { broken.push(match[0]); }
      }
    }
  }
  return broken;
}"""


def test_short_words_and_buttons_stay_whole_when_the_table_is_squeezed(browser: Browser):
    """
    **Feature: tables (XC-05)**
    **Property: in a seven-column admin table squeezed into a 1300px window with a long description and a very long account name, no
    word of four or more letters (project name, owner, month, button label) is cut across lines; the long unbroken account
    name still wraps inside its cell and the page does not scroll sideways.**
    """
    page = open_shell_page(browser, path="/projects", bundle_names=["pyc-site-shell"], api_stubs={}, content_html=TABLE, **DESKTOP)
    try:
        page.wait_for_selector("main table")
        page.wait_for_timeout(800)
        broken: List[str] = page.evaluate(_BROKEN_WORDS_JS)
        sideways = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
    finally:
        page.context.close()

    testbase.assert_equal((broken, sideways), ([], False))
    return


def test_the_project_user_and_enrollment_lists_mark_their_short_columns():
    """
    **Feature: tables (XC-05)**
    **Property: the All Projects list marks its name column ``min-name`` and its owner, counts and date columns ``nowrap``; the
    user list marks the username ``min-name``; the enrollment-token list marks its project ``min-name`` and its dates ``nowrap``
    (the templates, which is where the cut-off words came from).**
    """
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    while not os.path.isdir(os.path.join(root, "source", "site")) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    base = os.path.join(root, "source", "site", "ccai", "pychestrate", "webservice", "webinterface", "blueprints")
    texts = {}
    for key, parts in (
        ("projects", ("projects", "templates", "projects", "projects", "list.html")),
        ("users", ("config", "templates", "config", "users", "list.html")),
        ("tokens", ("config", "templates", "config", "enrollment", "list.html")),
    ):
        with open(os.path.join(base, *parts), encoding="utf-8") as handle:
            texts[key] = handle.read()

    testbase.assert_equal(
        (
            texts["projects"].count('class="min-name"'), texts["projects"].count('class="nowrap"'),
            texts["users"].count('class="min-name"'),
            texts["tokens"].count('class="min-name"'), texts["tokens"].count('class="nowrap"'),
        ),
        (1, 4, 1, 1, 2),
    )
    return
