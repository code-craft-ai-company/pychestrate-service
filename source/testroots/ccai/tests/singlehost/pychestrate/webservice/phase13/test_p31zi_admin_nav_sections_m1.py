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


def test_the_secrets_screens_sit_together_under_configuration():
    """
    **Feature: admin menu (ADM-39)**
    **Property: the secret scopes and the (legacy) secrets entries are
    next to each other, with the variables, under Configuration, instead of
    being scattered through the list.**
    """
    entries = _admin_entries()
    ids = [entry.entry_id for entry in entries if entry.section == "Configuration"]
    scopes, secrets = ids.index("admin.scopes"), ids.index("admin.secrets")

    testbase.assert_equal((abs(scopes - secrets), "admin.variables" in ids), (1, True))
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
