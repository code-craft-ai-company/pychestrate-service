"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_role_menu_preview_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The role form previews which menu entries the ticked permissions would show (ADM-06).

.. moduleauthor:: Code Craft AI LLC

A menu entry is shown only to someone who holds every permission it needs, so a role with half of a pair gets no entry and no message. Under
each permission the form now says what the menu also needs; this adds the answer to "what will this role actually see?" as the boxes are
ticked: the entries the role shows, and the ones not shown yet because part of what they need is not ticked, each with the permission still missing. The preview comes
from the same navigation manifest, so it cannot disagree with the menu. It is tested in a browser, on the real picker markup.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from types import SimpleNamespace
from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import _CORE_PERMISSION_DESCRIPTIONS
from ccai.pychestrate.webservice.webinterface.foundation.permission_presentation import menu_preview_data
from ccai.pychestrate.webservice.webinterface.site_shell import nav_manifest
from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_fixture_page,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import strict_environment


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 1000}}


def _picker_html(selected: List[str]) -> str:
    catalog = [SimpleNamespace(id=key, name=key, description=text) for key, text in _CORE_PERMISSION_DESCRIPTIONS.items()]
    template = strict_environment().from_string(
        '{% import "site_shell/_macros.html" as ui %}{{ ui.permission_picker(permissions, selected) }}'
        '{% include "site_shell/_permission_filter.html" %}'
    )
    return template.render(permissions=catalog, selected=selected)


def _read(browser: Browser, selected: List[str], ticks: List[str]) -> Dict[str, Any]:
    page = open_fixture_page(browser, body_html=_picker_html(selected), **DESKTOP)
    try:
        for key in ticks:
            page.check('input[name="permission_keys"][value="{}"]'.format(key))
        page.wait_for_timeout(100)
        return {
            "visible": page.locator('[data-role="menu-preview"]').is_visible(),
            "shown": " ".join(page.locator('[data-role="menu-shown"]').inner_text().split()),
            "held": " ".join(page.locator('[data-role="menu-held"]').inner_text().split()) if page.locator('[data-role="menu-held"]').is_visible() else "",
        }
    finally:
        page.context.close()


def test_the_data_lists_every_entry_that_depends_on_a_permission_with_its_group_and_keys():
    """
    **Feature: role menu preview (ADM-06)**
    **Property: the preview data has an entry for every manifest entry that needs a permission, labelled with its group ("Admin › Users"),
    carrying its own keys and its group's; and a phrase, as the picker names it, for every key used.**
    """
    data = menu_preview_data()
    by_label = {entry["label"]: entry["needs"] for entry in data["entries"]}
    dependent = [entry for entry in nav_manifest.NAV_ENTRIES if len(entry.required_permissions) > 0]
    used = {key for entry in data["entries"] for key in entry["needs"]}

    testbase.assert_equal(
        (
            len(data["entries"]) >= len(dependent), by_label["Admin › Users"], by_label["Insights › Dashboards"],
            by_label["Fleet › Resources and Pools"], used == set(data["phrases"]),
            data["phrases"]["system:ui.admin.view"],
        ),
        (
            True, ["system:users.read", "system:ui.admin.view"], ["system:metrics.read", "system:dashboards.read"],
            ["system:resources.read", "system:resource_pools.read"], True, "Interface › Admin · see in the menu",
        ),
    )
    return


def test_the_markup_carries_the_data_and_starts_hidden_until_script_runs():
    """
    **Feature: role menu preview (ADM-06)**
    **Property: the rendered picker holds the preview data as a JSON island that parses and matches, and the preview region is ``hidden``
    in the markup (without script nothing misleading is shown).**
    """
    html_text = _picker_html([])
    island = re.search(r'<script type="application/json" data-role="menu-preview-data">(.*?)</script>', html_text, re.S)
    parsed = json.loads(island.group(1)) if island is not None else None

    testbase.assert_equal(
        (parsed == json.loads(json.dumps(menu_preview_data())), 'data-role="menu-preview" role="status" aria-live="polite" hidden' in html_text),
        (True, True),
    )
    return


def test_ticking_half_of_a_pair_holds_the_entry_back_and_names_what_is_missing(browser: Browser):
    """
    **Feature: role menu preview (ADM-06)**
    **Property: with nothing ticked the preview says no entry is shown and lists none as not shown yet; ticking ``users.read`` alone lists
    "Admin › Users" as not shown yet and names "Interface › Admin · see in the menu"; ticking ``ui.admin.view`` as well shows it (and the Admin
    overview) and no longer lists it, while the other Admin entries are listed with the permission each still needs.**
    """
    nothing = _read(browser, [], [])
    half = _read(browser, [], ["system:users.read"])
    both = _read(browser, [], ["system:users.read", "system:ui.admin.view"])

    testbase.assert_equal(
        (
            nothing["visible"], nothing["shown"], nothing["held"],
            half["shown"], half["held"],
            "Admin › Users" in both["shown"], "Admin › Overview" in both["shown"], "Admin › Users" in both["held"],
            "Admin › Roles (needs Roles and access › View)" in both["held"],
        ),
        (
            True, "Menu entries this role shows: none yet.", "",
            "Menu entries this role shows: none yet.",
            "Not shown yet: Admin › Users (needs Interface › Admin · see in the menu).",
            True, True, False, True,
        ),
    )
    return


def test_both_halves_of_resources_and_pools_and_a_role_that_is_being_edited(browser: Browser):
    """
    **Feature: role menu preview (ADM-06)**
    **Property: ``resources.read`` shows "Fleet › Older Resources" (it needs only that) and lists "Fleet › Resources and Pools" as not shown
    yet, naming "Resource pools › View"; ticking ``resource_pools.read`` shows it. A role opened with ``metrics.read`` already ticked lists
    Dashboards as not shown yet on load, naming "Dashboards › View".**
    """
    first = _read(browser, [], ["system:resources.read"])
    second = _read(browser, [], ["system:resources.read", "system:resource_pools.read"])
    editing = _read(browser, ["system:metrics.read"], [])

    testbase.assert_equal(
        (
            "Fleet › Older Resources" in first["shown"], "Fleet › Resources and Pools" in first["shown"],
            "Fleet › Resources and Pools (needs Resource pools › View)" in first["held"],
            "Fleet › Resources and Pools" in second["shown"], "Resources and Pools" in second["held"],
            editing["held"],
        ),
        (
            True, False, True, True, False,
            "Not shown yet: Insights › Dashboards (needs Dashboards › View).",
        ),
    )
    return
