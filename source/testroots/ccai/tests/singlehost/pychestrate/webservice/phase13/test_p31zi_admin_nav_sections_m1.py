"""
.. module:: test_p31zi_admin_nav_sections_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Admin menu is split into sections (ADM-39).

.. moduleauthor:: Code Craft AI LLC

The Admin group listed fifteen entries in one flat run, with secrets split
across two places. The manifest now labels each admin entry with a section
(People & access, Configuration, Fleet enrollment, Platform), keeps the
entries of a section together, and the sidebar writes the section's name
above them. The Overview stays first, with no heading.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    GROUP_ADMIN,
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

SECTIONS: List[str] = ["People & access", "Configuration", "Fleet enrollment", "Platform"]


def _admin_entries() -> List[Any]:
    return [entry for entry in NAV_ENTRIES if entry.group_id == GROUP_ADMIN]


def test_the_admin_entries_are_kept_together_by_section_in_a_fixed_order():
    """
    **Feature: admin menu (ADM-39)**
    **Property: the Overview is first and has no section; every other
    admin entry has one; the sections come in the order People & access,
    Configuration, Fleet enrollment, Platform, and no section is split
    into two runs.**
    """
    entries = _admin_entries()
    runs: List[str] = []
    for entry in entries[1:]:
        if len(runs) == 0 or runs[-1] != entry.section:
            runs.append(entry.section)

    testbase.assert_equal(
        (entries[0].entry_id, entries[0].section, [entry.section for entry in entries[1:] if entry.section == ""], runs),
        ("admin.overview", "", [], SECTIONS),
    )
    return


def test_the_admin_menu_has_no_legacy_secret_entries_and_the_vault_is_still_under_system():
    """
    **Feature: admin menu (ADM-39, ADM-07)**
    **Property: Admin has no "Secrets (legacy)" or "Secret Scopes (legacy)" entry (those pages are gone), the Variables entry is still under Configuration, and the vault
    (``system.secrets``, at ``/secrets``) is still in the menu.**
    """
    entries = _admin_entries()
    configuration = [entry.entry_id for entry in entries if entry.section == "Configuration"]
    everywhere = {entry.entry_id: entry.route for entry in NAV_ENTRIES}

    testbase.assert_equal(
        ("admin.scopes" in everywhere, "admin.secrets" in everywhere, "admin.variables" in configuration, everywhere.get("system.secrets")),
        (False, False, True, "/secrets"),
    )
    return


def test_the_navigation_answer_carries_the_section_only_where_there_is_one():
    """
    **Feature: admin menu (ADM-39)**
    **Property: in the navigation the service answers with, admin entries
    carry a section and other groups' entries do not, so other menus are
    unchanged.**
    """
    manifest = build_navigation_manifest(held_permissions=all_navigation_permissions())
    groups = {group["group_id"]: group["entries"] for group in manifest["groups"]}
    admin_sections = [entry.get("section") for entry in groups[GROUP_ADMIN]]
    others = [entry for group_id, entries in groups.items() if group_id != GROUP_ADMIN for entry in entries]

    testbase.assert_equal(
        (admin_sections[0], set(admin_sections[1:]) == set(SECTIONS), any("section" in entry for entry in others)),
        (None, True, False),
    )
    return


#: JS: the Admin panel's list, as ``[{heading: bool, text: str}]``.
ADMIN_PANEL_JS: str = r"""
() => {
  const panel = Array.from(document.querySelectorAll('[role=group]')).find((el) => el.getAttribute('aria-label') === 'Admin');
  if (!panel) { return null; }
  return Array.from(panel.querySelectorAll('li')).map((li) => ({
    heading: li.classList.contains('pyc-site-shell__sidebar-section'),
    text: li.textContent.trim(),
  }));
}
"""


def test_the_sidebar_writes_each_section_heading_above_its_entries(browser: Browser):
    """
    **Feature: admin menu (ADM-39)**
    **Property: on an admin page the Admin group lists the Overview, then
    four headings in order, each followed by its entries (Users under
    People & access, Variables under Configuration, Enrollment Tokens under
    Fleet enrollment, System Health under Platform).**
    """
    page = open_shell_page(browser, path="/admin/users", **DESKTOP)
    try:
        items = page.evaluate(ADMIN_PANEL_JS)
        headings = [item["text"] for item in items if item["heading"]]
        following: Dict[str, str] = {}
        for index, item in enumerate(items):
            if item["heading"]:
                following[item["text"]] = items[index + 1]["text"]
        testbase.assert_equal(
            (items[0], headings, following),
            (
                {"heading": False, "text": "Overview"}, SECTIONS,
                {"People & access": "Users", "Configuration": "Variables", "Fleet enrollment": "Enrollment Tokens",
                 "Platform": "System Health"},
            ),
        )
    finally:
        page.context.close()
    return


#: Where the text of each heading and entry in the open Admin panel starts, in pixels from the left of the page.
INDENT_JS = """() => {
  const panel = Array.from(document.querySelectorAll('.pyc-site-shell__sidebar-panel')).find((p) => !p.hidden && p.querySelector('.pyc-site-shell__sidebar-section'));
  const rows = [];
  for (const li of panel.querySelectorAll('.pyc-site-shell__sidebar-panel-list > li')) {
    const heading = li.classList.contains('pyc-site-shell__sidebar-section');
    const node = heading ? li : li.firstElementChild;
    const range = document.createRange();
    range.selectNodeContents(node);
    rows.push({heading, text: node.textContent.trim(), left: Math.round(range.getBoundingClientRect().left)});
  }
  return rows;
}"""


def test_entries_under_a_section_heading_are_indented_past_it(browser: Browser):
    """
    **Feature: admin menu (ADM-39)**
    **Property: in the open Admin panel every entry under a section heading starts further right than the heading (by at least 8 px), the entries of one
    section share one indent, and the Overview, which sits under no heading, starts where the headings do, so the hierarchy reads group, heading, entries.**
    """
    page = open_shell_page(browser, path="/admin/users", **DESKTOP)
    try:
        rows = page.evaluate(INDENT_JS)
    finally:
        page.context.close()
    heading_left: Dict[str, int] = {}
    entry_lefts: Dict[str, List[int]] = {}
    current = ""
    for row in rows:
        if row["heading"]:
            current = row["text"]
            heading_left[current] = row["left"]
            entry_lefts[current] = []
        elif current != "":
            entry_lefts[current].append(row["left"])
    overview_left = rows[0]["left"]
    summary = {
        name: (all(left - heading_left[name] >= 8 for left in lefts), len(set(lefts)) == 1, len(lefts) > 0)
        for name, lefts in entry_lefts.items()
    }
    testbase.assert_equal(
        (rows[0]["text"], overview_left == min(heading_left.values()), list(summary.keys()), set(summary.values())),
        ("Overview", True, SECTIONS, {(True, True, True)}),
    )
    return


def test_a_group_without_sections_gets_no_headings(browser: Browser):
    """
    **Feature: admin menu (ADM-39)**
    **Property: the Fleet group, whose entries have no section, shows no
    section heading.**
    """
    page = open_shell_page(browser, path="/pods", **DESKTOP)
    try:
        count = page.evaluate(
            "() => document.querySelectorAll('[role=group][aria-label=Fleet] .pyc-site-shell__sidebar-section').length"
        )
        testbase.assert_equal(count, 0)
    finally:
        page.context.close()
    return
